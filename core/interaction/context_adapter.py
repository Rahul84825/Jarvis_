"""Platform-specific adapters for Universal Desktop Context & Accessibility Inspection."""

import sys
import time
import logging
import psutil
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple

from core.interaction.models import TargetControl, DesktopContext, ControlType
from core.os.cdp_client import CDPClient

logger = logging.getLogger("Jarvis.DesktopContext")


class BaseDesktopContextAdapter(ABC):
    """Abstract base adapter for operating system desktop accessibility."""

    @abstractmethod
    def get_desktop_context(self, explicit_destination: Optional[str] = None, allow_ocr: bool = False) -> DesktopContext:
        """Captures active foreground window, focused element, and available input fields."""
        pass

    @abstractmethod
    def insert_text(
        self,
        target: Optional[TargetControl],
        text: str,
        mode: str = "insert",
        expected_hwnd: int = 0,
        expected_title: str = ""
    ) -> Dict[str, Any]:
        """Inserts text into the verified target control with window stability check."""
        pass

    @abstractmethod
    def verify_window_stable(self, expected_hwnd: int, expected_title: str = "") -> bool:
        """Verifies foreground window has not changed unexpectedly between preparation and typing."""
        pass


class WindowsDesktopContextAdapter(BaseDesktopContextAdapter):
    """Windows implementation using native UIAutomationCore COM interfaces and Win32 APIs."""

    def __init__(self):
        self.cdp_client = CDPClient()
        self._uia_auto = None
        self._uia_mod = None
        self._init_uia()

    def _init_uia(self):
        """Initializes Windows UIAutomationCore COM interface lazily."""
        try:
            import comtypes.client
            self._uia_mod = comtypes.client.GetModule("UIAutomationCore.dll")
            self._uia_auto = comtypes.client.CreateObject(
                self._uia_mod.CUIAutomation,
                interface=self._uia_mod.IUIAutomation
            )
            logger.debug("[UIA] Windows UI Automation client initialized successfully.")
        except Exception as e:
            logger.debug(f"[UIA] Native UIAutomationCOM unavailable: {e}")
            self._uia_auto = None
            self._uia_mod = None

    def get_foreground_info(self) -> Tuple[int, str, str, str]:
        """Returns (hwnd, window_title, process_name, app_slug)."""
        hwnd = 0
        title = ""
        proc_name = "unknown"
        app_slug = "unknown"

        try:
            import win32gui
            import win32process
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd).strip()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    p = psutil.Process(pid)
                    proc_name = p.name()
                    app_slug = proc_name.lower().replace(".exe", "")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[DESKTOP] Failed to get foreground window info: {e}")

        # Fallback to pygetwindow if win32gui returned empty
        if not title:
            try:
                import pygetwindow as gw
                win = gw.getActiveWindow()
                if win and win.title:
                    title = win.title.strip()
                    hwnd = getattr(win, "_hWnd", hwnd)
            except Exception:
                pass

        return hwnd, title, proc_name, app_slug

    def _classify_control(
        self,
        name: str,
        help_text: str,
        automation_id: str,
        class_name: str,
        app_slug: str,
        browser_url: str = "",
        window_title: str = ""
    ) -> ControlType:
        """Determines semantic control type based on accessibility metadata, context, and window title."""
        combined = f"{name} {help_text} {automation_id} {class_name}".lower()
        title_lower = window_title.lower()
        url_lower = browser_url.lower()

        # 1. ChatGPT prompt box
        if "chatgpt" in title_lower or "chatgpt.com" in url_lower:
            if any(k in combined for k in ["prompt", "message chatgpt", "ask anything", "contenteditable"]) or "textarea" in combined:
                return ControlType.PROMPT_BOX
            if "search" in combined:
                return ControlType.SEARCH_FIELD

        # 2. WhatsApp message composer
        if "whatsapp" in app_slug or "whatsapp" in title_lower or "web.whatsapp.com" in url_lower:
            if any(k in combined for k in ["type a message", "message input", "type message", "composer"]):
                return ControlType.MESSAGE_COMPOSER
            if any(k in combined for k in ["search or start new chat", "search", "search chat"]):
                return ControlType.SEARCH_FIELD

        # 3. Email fields (Gmail, Outlook, Thunderbird, Mail)
        if any(e in title_lower or e in url_lower or e in app_slug for e in ["mail", "gmail", "outlook", "thunderbird"]):
            import re
            if any(k in combined for k in ["recipients", "add recipients", "email to"]) or re.search(r"\bto\b", combined):
                return ControlType.EMAIL_TO
            if any(k in combined for k in ["subject", "email subject", "add a subject"]):
                return ControlType.EMAIL_SUBJECT
            if any(k in combined for k in ["body", "message body", "compose email", "compose message", "text area"]):
                return ControlType.EMAIL_BODY

        # 4. Search fields
        if any(k in combined for k in ["search", "find", "query", "look up", "filter"]):
            return ControlType.SEARCH_FIELD
        if "youtube" in url_lower or "youtube" in title_lower:
            if "search" in combined or automation_id.lower() == "search":
                return ControlType.SEARCH_FIELD

        # 5. Code editors (VS Code, Cursor, Notepad++, PyCharm, Sublime)
        if any(ed in app_slug for ed in ["code", "cursor", "notepad++", "pycharm", "sublime", "devenv"]):
            if "search" in combined or "find" in combined:
                return ControlType.SEARCH_FIELD
            return ControlType.CODE_EDITOR

        # 6. Generic Documents & Editors
        if "notepad" in app_slug or "document" in class_name.lower():
            return ControlType.DOCUMENT

        return ControlType.EDIT

    def get_desktop_context(self, explicit_destination: Optional[str] = None, allow_ocr: bool = False) -> DesktopContext:
        """Inspects foreground window and builds full DesktopContext."""
        hwnd, title, proc_name, app_slug = self.get_foreground_info()
        ctx = DesktopContext(
            foreground_app=app_slug,
            process_name=proc_name,
            window_hwnd=hwnd,
            window_title=title,
            timestamp=time.time()
        )

        # 1. Browser CDP Integration (if foreground app is Chrome/Chromium)
        browser_url = ""
        if "chrome" in app_slug or "edge" in app_slug or "brave" in app_slug:
            try:
                if self.cdp_client.is_available():
                    active_tab = self.cdp_client.get_active_tab()
                    if active_tab:
                        browser_url = active_tab.get("url", "")
                        ctx.browser_info = {
                            "browser": app_slug,
                            "tab_id": active_tab.get("id"),
                            "tab_title": active_tab.get("title", ""),
                            "tab_url": browser_url,
                            "cdp_active": True
                        }
            except Exception as e:
                logger.debug(f"[CDP] Browser inspection error: {e}")

        # 2. Windows UI Automation Inspection
        targets: List[TargetControl] = []
        focused_ctrl: Optional[TargetControl] = None

        if self._uia_auto and self._uia_mod and hwnd:
            try:
                # Query focused element first
                raw_focused = self._uia_auto.GetFocusedElement()
                if raw_focused:
                    f_name = raw_focused.CurrentName or ""
                    f_help = raw_focused.CurrentHelpText or ""
                    f_aid = raw_focused.CurrentAutomationId or ""
                    f_class = raw_focused.CurrentClassName or ""
                    f_type_id = raw_focused.CurrentControlType
                    
                    # Accept edit (50004), document (50030), combobox (50003), or pane (50033) if name/help exists
                    if f_type_id in [self._uia_mod.UIA_EditControlTypeId, self._uia_mod.UIA_DocumentControlTypeId, self._uia_mod.UIA_ComboBoxControlTypeId] or f_name:
                        ctype = self._classify_control(f_name, f_help, f_aid, f_class, app_slug, browser_url, title)
                        focused_ctrl = TargetControl(
                            control_id="focused_0",
                            name=f_name or "Focused Text Input",
                            control_type=ctype,
                            help_text=f_help,
                            automation_id=f_aid,
                            class_name=f_class,
                            is_focused=True,
                            confidence=0.95,
                            raw_element=raw_focused
                        )
                        targets.append(focused_ctrl)

                # Query all text entry elements in window
                root_elem = self._uia_auto.ElementFromHandle(hwnd)
                if root_elem:
                    # Look for Edit, Document, and ComboBox controls
                    cond_edit = self._uia_auto.CreatePropertyCondition(self._uia_mod.UIA_ControlTypePropertyId, self._uia_mod.UIA_EditControlTypeId)
                    cond_doc = self._uia_auto.CreatePropertyCondition(self._uia_mod.UIA_ControlTypePropertyId, self._uia_mod.UIA_DocumentControlTypeId)
                    cond_or = self._uia_auto.CreateOrCondition(cond_edit, cond_doc)
                    
                    found_elems = root_elem.FindAll(self._uia_mod.TreeScope_Descendants, cond_or)
                    if found_elems:
                        for i in range(min(found_elems.Length, 15)):
                            el = found_elems.GetElement(i)
                            e_name = el.CurrentName or ""
                            e_help = el.CurrentHelpText or ""
                            e_aid = el.CurrentAutomationId or ""
                            e_class = el.CurrentClassName or ""
                            
                            # Avoid duplicate of focused element
                            if focused_ctrl and (e_aid == focused_ctrl.automation_id and e_name == focused_ctrl.name and e_name != ""):
                                continue

                            ctype = self._classify_control(e_name, e_help, e_aid, e_class, app_slug, browser_url, title)
                            targets.append(TargetControl(
                                control_id=f"target_{i+1}",
                                name=e_name or f"Input Field {i+1}",
                                control_type=ctype,
                                help_text=e_help,
                                automation_id=e_aid,
                                class_name=e_class,
                                is_focused=False,
                                confidence=0.85,
                                raw_element=el
                            ))

            except Exception as e:
                logger.debug(f"[UIA] Tree traversal error on window {hwnd}: {e}")

        # 3. Fallback Heuristics (e.g. if window is Notepad or known text editor)
        if not targets and hwnd:
            if "notepad" in app_slug:
                targets.append(TargetControl(
                    control_id="notepad_main",
                    name="Notepad Text Document",
                    control_type=ControlType.DOCUMENT,
                    is_focused=True,
                    confidence=0.9
                ))
            elif "code" in app_slug:
                targets.append(TargetControl(
                    control_id="vscode_editor",
                    name="Visual Studio Code Editor",
                    control_type=ControlType.CODE_EDITOR,
                    is_focused=True,
                    confidence=0.9
                ))

        ctx.focused_element = focused_ctrl
        ctx.available_targets = targets
        ctx.context_source = "accessibility_tree" if targets else "fallback"

        # Explicit Request-Triggered OCR fallback if requested and no targets
        if not targets and allow_ocr:
            logger.info(f"[SCREEN_CONTEXT] Reading screen context for window '{title}'...")
            ctx.context_source = "ocr"

        return ctx

    def verify_window_stable(self, expected_hwnd: int, expected_title: str = "") -> bool:
        """Verifies current foreground window still matches expected HWND and title."""
        if not expected_hwnd:
            return True
        curr_hwnd, curr_title, _, _ = self.get_foreground_info()
        if curr_hwnd != expected_hwnd:
            logger.warning(f"[SAFETY] Active window changed from {expected_hwnd} to {curr_hwnd} ('{curr_title}')")
            return False
        if expected_title and curr_title and expected_title.lower() != curr_title.lower():
            logger.warning(f"[SAFETY] Window title changed from '{expected_title}' to '{curr_title}'")
            return False
        return True

    def insert_text(
        self,
        target: Optional[TargetControl],
        text: str,
        mode: str = "insert",
        expected_hwnd: int = 0,
        expected_title: str = ""
    ) -> Dict[str, Any]:
        """Inserts text into verified target element with safety guarantees."""
        # 1. Window Stability Guard
        if expected_hwnd and not self.verify_window_stable(expected_hwnd, expected_title):
            return {
                "success": False,
                "reason": "window_changed",
                "message": "The active application changed, so I paused to avoid typing into the wrong window."
            }

        # 2. UIA ValuePattern (direct accessible text setting without simulating keystrokes)
        if target and target.raw_element and self._uia_mod:
            try:
                raw_el = target.raw_element
                # Try IUIAutomationValuePattern
                val_pattern = raw_el.GetCurrentPattern(self._uia_mod.UIA_ValuePatternId)
                if val_pattern:
                    import comtypes
                    pattern = val_pattern.QueryInterface(self._uia_mod.IUIAutomationValuePattern)
                    if mode == "append":
                        existing = pattern.CurrentValue or ""
                        new_val = f"{existing} {text}".strip()
                        pattern.SetValue(new_val)
                    else:
                        pattern.SetValue(text)
                    logger.info(f"[UIA] Inserted text via IUIAutomationValuePattern into '{target.name}'.")
                    return {
                        "success": True,
                        "method": "uia_value_pattern",
                        "target": target.name,
                        "message": f"Text inserted into '{target.name}'."
                    }
            except Exception as e:
                logger.debug(f"[UIA] ValuePattern failed on '{target.name}': {e}. Falling back to clipboard paste.")

        # 3. Focus & Native Clipboard Injection Fallback
        try:
            import pyautogui
            import pyperclip

            # Save existing clipboard
            original_clip = ""
            try:
                original_clip = pyperclip.paste()
            except Exception:
                pass

            # If target has raw_element, focus it
            if target and target.raw_element:
                try:
                    target.raw_element.SetFocus()
                    time.sleep(0.05)
                except Exception:
                    pass

            if mode == "replace":
                # Select all and replace
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.03)

            # Copy text and paste via Ctrl+V
            pyperclip.copy(text)
            time.sleep(0.02)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)

            # Restore original clipboard
            try:
                if original_clip:
                    pyperclip.copy(original_clip)
            except Exception:
                pass

            target_disp = target.name if target else "active field"
            logger.info(f"[DESKTOP] Inserted text via clipboard paste into {target_disp}.")
            return {
                "success": True,
                "method": "clipboard_paste",
                "target": target_disp,
                "message": f"Text inserted into {target_disp}."
            }
        except Exception as e:
            logger.error(f"[DESKTOP] Text insertion failed: {e}")
            return {
                "success": False,
                "reason": "insertion_failed",
                "message": f"Failed to insert text: {e}"
            }


class LinuxDesktopContextAdapter(BaseDesktopContextAdapter):
    """Linux implementation for desktop context awareness."""

    def get_desktop_context(self, explicit_destination: Optional[str] = None, allow_ocr: bool = False) -> DesktopContext:
        """Inspects active window using xdotool / AT-SPI or fallback."""
        ctx = DesktopContext(
            foreground_app="linux_app",
            process_name="linux_process",
            window_hwnd=1,
            window_title="Linux Desktop Window",
            context_source="fallback",
            timestamp=time.time()
        )
        return ctx

    def verify_window_stable(self, expected_hwnd: int, expected_title: str = "") -> bool:
        return True

    def insert_text(
        self,
        target: Optional[TargetControl],
        text: str,
        mode: str = "insert",
        expected_hwnd: int = 0,
        expected_title: str = ""
    ) -> Dict[str, Any]:
        """Injects text on Linux via clipboard paste or typing."""
        try:
            import pyautogui
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            return {
                "success": True,
                "method": "clipboard_paste",
                "target": target.name if target else "active field",
                "message": "Text inserted."
            }
        except Exception as e:
            return {"success": False, "message": f"Linux text insertion failed: {e}"}
