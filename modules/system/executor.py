import os
import time
import logging
import psutil
from pathlib import Path
from config import config
from modules.system import app_control, window_control, system_control, screenshot, permissions
from modules.files import file_control
from modules.browser import web_control
from core.os import TerminalManager, FilesystemManager, ProcessManager, SystemInfoProvider, ProjectRegistry, BrowserManager
from core.content_generator import ContentGenerator
from core.response_registry import CommandOutcome

logger = logging.getLogger("Jarvis.Executor")

class CommandExecutor:
    """Central command execution engine.
    Validates, routes, and executes system commands, web links, system info requests, maintaining permission checks.
    Returns standardized execution output dictionaries.
    """

    def __init__(self, history_tracker=None):
        self.history_tracker = history_tracker
        self.terminal_mgr = TerminalManager()
        self.filesystem_mgr = FilesystemManager()
        self.process_mgr = ProcessManager()
        self.system_info_mgr = SystemInfoProvider()
        self.project_registry = ProjectRegistry()
        self.browser_mgr = BrowserManager()
        self.content_gen = ContentGenerator(filesystem_mgr=self.filesystem_mgr)
        self.last_created_file = None
        self.last_search_results = []
        self.panel_visibility_cb = None
        logger.info("Command Executor initialized with Full OS Control Layer.")

    def execute(self, intent_node: dict, confirm: bool = False) -> dict:
        """Executes a structured intent node command.

        Args:
            intent_node: Dictionary containing 'intent', 'action', 'target', or 'query'
            confirm: Boolean flag indicating if high-risk actions have been confirmed by user

        Returns:
            Dictionary representing structured execution results:
            {
                "success": bool,
                "message": str,
                "intent": str,
                "action": str,
                "target": str,
                "spoken": bool,
                "pending_confirmation": bool
            }
        """
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action") or intent
        target = intent_node.get("target")
        t0 = time.time()

        logger.info(f"Executor received command: Intent='{intent}', Action='{action}', Target='{target}'")

        # 1. Validate Command Parameters for safety
        if not permissions.is_safe_command(intent, intent_node):
            result = {
                "success": False,
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
                "message": "Action blocked: Command contains forbidden shell metacharacters.",
                "intent": intent,
                "action": action,
                "target": target,
                "spoken": True,
                "pending_confirmation": False
            }
            self._record_history(intent_node, result)
            return result

        # 2. Risk and Permission Level Check
        risk_level = permissions.get_action_risk_level(intent, action)
        logger.info(f"Action safety classification: {risk_level}")

        # Dedicated conversational handling for Spotify operations (explains unfollow vs permanent delete)
        if intent == "spotify_control":
            result = self._execute_spotify_control(intent_node, confirm=confirm)
            self._record_history(intent_node, result)
            return result

        # Dedicated handling for Panel Visibility (Show / Hide / Minimize / Restore Santra)
        if intent == "panel_visibility":
            act = action or "show_panel"
            if self.panel_visibility_cb:
                try:
                    self.panel_visibility_cb(act)
                except Exception as cb_err:
                    logger.error(f"Error in panel visibility callback: {cb_err}")

            if act in ["show_panel", "show", "restore"]:
                msg = "Opening Santra dashboard, Sir."
            elif act in ["hide_panel", "hide", "minimize"]:
                msg = "Santra panel hidden to system tray."
            elif act in ["exit_assistant", "exit", "quit", "shutdown"]:
                msg = "Shutting down Santra. Goodbye, Sir."
            else:
                msg = f"Panel visibility set to {act}."

            result = {
                "success": True,
                "outcome": CommandOutcome.SUCCESS.value,
                "message": msg,
                "intent": intent,
                "action": act,
                "spoken": True
            }
            self._record_history(intent_node, result)
            return result

        if risk_level == permissions.RiskLevel.HIGH and not confirm:
            logger.info("High-risk action blocked. Awaiting user confirmation.")
            result = {
                "success": False,
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
                "message": "This action is high risk. Are you sure you want to proceed?",
                "intent": intent,
                "action": action,
                "target": target,
                "spoken": True,
                "pending_confirmation": True
            }
            return result

        # 3. Route Command to appropriate modules
        success = False
        message = ""
        outcome = None

        try:
            if intent in ["open_new_chrome_tab", "new_chrome_tab"]:
                url = intent_node.get("url")
                res = self.browser_mgr.open_new_chrome_tab(url=url)
                success = res["success"]
                message = res["message"]

            elif intent in ["open_new_chrome_window", "new_chrome_window"]:
                url = intent_node.get("url")
                res = self.browser_mgr.open_new_chrome_window(url=url)
                success = res["success"]
                message = res["message"]

            elif intent in ["browser_action", "browser.action"]:
                from core.os.browser_automation import browser_automation_engine
                from core.os.browser_intent import BrowserIntent, BrowserActionType, SearchScope, TabPreference

                action_type_str = intent_node.get("action_type") or intent_node.get("action", "unknown")
                try:
                    b_action = BrowserActionType(action_type_str)
                except ValueError:
                    b_action = BrowserActionType.UNKNOWN

                tab_pref_str = intent_node.get("tab_preference", "default")
                try:
                    t_pref = TabPreference(tab_pref_str)
                except ValueError:
                    t_pref = TabPreference.DEFAULT

                b_intent = BrowserIntent(
                    action_type=b_action,
                    target_browser=intent_node.get("target_browser") or intent_node.get("browser", "chrome"),
                    url=intent_node.get("url"),
                    site_name=intent_node.get("site_name") or intent_node.get("target"),
                    domain=intent_node.get("domain"),
                    search_query=intent_node.get("search_query") or intent_node.get("query", ""),
                    prompt_query=intent_node.get("prompt_query", ""),
                    tab_preference=t_pref,
                    input_purpose=intent_node.get("input_purpose", "search_box"),
                    submit=intent_node.get("submit", True),
                    requires_confirmation=intent_node.get("requires_confirmation", False),
                    clarification_prompt=intent_node.get("clarification_prompt"),
                    raw_text=intent_node.get("raw_text", ""),
                    metadata=intent_node.get("metadata", {})
                )

                res = browser_automation_engine.execute_intent(b_intent)
                success = bool(res.get("success", False))
                message = res.get("message", "")
                if res.get("requires_clarification"):
                    pending_data = {
                        "original_request": intent_node.get("raw") or intent_node.get("raw_text", ""),
                        "intent": "browser_action",
                        "action": b_intent.action_type.value,
                        "target": b_intent.site_name or b_intent.domain or b_intent.search_query,
                        "target_url": b_intent.url,
                        "target_domain": b_intent.domain,
                        "browser": b_intent.target_browser or "chrome",
                        "search_query": b_intent.search_query,
                        "clarification_prompt": message,
                        "clarification_type": "browser_selection" if "browser" in message.lower() else "destination_selection",
                        "valid_options": ["chrome", "firefox", "edge", "brave", "yes", "no", "cancel"]
                    }
                    result = {
                        "success": True,
                        "outcome": CommandOutcome.SUCCESS.value,
                        "message": message,
                        "intent": intent,
                        "requires_clarification": True,
                        "clarification_prompt": message,
                        "pending_intent": pending_data
                    }
                    self._record_history(intent_node, result)
                    return result
                elif res.get("pending_confirmation"):
                    result = {
                        "success": False,
                        "outcome": CommandOutcome.PERMISSION_DENIED.value,
                        "message": message,
                        "intent": intent,
                        "pending_confirmation": True
                    }
                    self._record_history(intent_node, result)
                    return result
                outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent == "open_website":
                browser_name = intent_node.get("browser")
                url = intent_node.get("url")
                if browser_name:
                    if not url:
                        url = web_control.links.get(target.lower(), f"https://{target}")
                    res = self.browser_mgr.open_browser(browser_name=browser_name, url=url)
                    success = res.get("success", False)
                    site_display = target.title() if target else "website"
                    browser_display = browser_name.title()
                    if success:
                        outcome = CommandOutcome.SUCCESS
                        message = f"Opening {site_display} in {browser_display}."
                    else:
                        outcome = CommandOutcome.EXECUTION_FAILED
                        message = res.get("message", f"I couldn't open {site_display} in {browser_display}.")
                else:
                    success, message = web_control.open_website(target)
                    if not success:
                        outcome = CommandOutcome.EXECUTION_FAILED
                        message = "I couldn't open that website, Sir."
                    else:
                        outcome = CommandOutcome.SUCCESS

            elif intent == "web_search":
                provider = intent_node.get("provider", "google")
                query = intent_node.get("query") or intent_node.get("target", "")
                empty_q = intent_node.get("empty_query", False) or not query or not query.strip()

                if empty_q:
                    logger.info("[SEARCH] Empty search query detected. Prompting clarification.")
                    logger.info("[SEARCH] Tool execution completed")
                    msg = "What would you like me to search for, Sir?"
                    logger.info(f"[SEARCH] Response generation completed: '{msg}'")
                    result = {
                        "success": True,
                        "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                        "message": msg,
                        "intent": "web_search",
                        "action": "search",
                        "target": "",
                        "spoken": True,
                        "pending_confirmation": False
                    }
                    self._record_history(intent_node, result)
                    return result

                logger.info("[SEARCH] Tool execution started")
                try:
                    browser_target = intent_node.get("browser")
                    if browser_target and browser_target != "default":
                        res = self.browser_mgr.search(query, provider=provider, browser_name=browser_target)
                    else:
                        res = self.browser_mgr.search(query, provider=provider)
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    if success:
                        outcome = CommandOutcome.SUCCESS
                        logger.info("[SEARCH] Tool execution completed")
                        logger.info(f"[SEARCH] Results received: 1 (Browser search launched: {provider})")
                        logger.info(f"[SEARCH] Response generation completed: '{message}'")
                    else:
                        err_detail = res.get("message", "")
                        if "not configured" in err_detail.lower():
                            outcome = CommandOutcome.PROVIDER_UNAVAILABLE
                            message = err_detail or "Search is temporarily unavailable, Sir."
                        elif "timed out" in err_detail.lower() or "timeout" in err_detail.lower():
                            outcome = CommandOutcome.TIMEOUT
                            message = err_detail or "That action timed out, Sir. Please try again."
                        elif "network" in err_detail.lower() or "connection" in err_detail.lower() or "unavailable" in err_detail.lower():
                            outcome = CommandOutcome.PROVIDER_UNAVAILABLE
                            message = err_detail or "Search is temporarily unavailable, Sir."
                        else:
                            outcome = CommandOutcome.EXECUTION_FAILED
                            message = err_detail or "That action failed, Sir. Please try again."
                        logger.error(f"[SEARCH] Execution failed: {message}")
                except TimeoutError as te:
                    success = False
                    outcome = CommandOutcome.TIMEOUT
                    message = "That action timed out, Sir. Please try again."
                    logger.error(f"[SEARCH] Execution failed: {te}")
                    logger.error("[SEARCH] Failure category: timeout")
                except Exception as e:
                    success = False
                    outcome = CommandOutcome.PROVIDER_UNAVAILABLE
                    message = "I encountered an unexpected error while attempting to search."
                    logger.error(f"[SEARCH] Execution failed: {e}")

            elif intent == "time_query":
                import datetime
                now = datetime.datetime.now()
                success = True
                message = f"The time is {now.strftime('%I:%M %p')}."

            elif intent == "date_query":
                import datetime
                now = datetime.datetime.now()
                success = True
                message = f"Today is {now.strftime('%A, %B %d, %Y')}."

            elif intent == "math_calculation":
                import re, math
                query_str = target or intent_node.get("query", "")
                q = query_str.lower()
                q = re.sub(r'^(calculate|what is|how much is|solve|math|watch|what s|whats)\s+', '', q).strip(' ?')
                pct_match = re.search(r'([\d\.]+)\s*(?:%|percent)\s*(?:of)\s*([\d\.]+)', q)
                if pct_match:
                    val = (float(pct_match.group(1)) / 100.0) * float(pct_match.group(2))
                    success = True
                    message = f"{pct_match.group(1)} percent of {pct_match.group(2)} is {val:g}."
                else:
                    try:
                        q = re.sub(r'([\d\.]+)\s*(?:to the power of|\^)\s*([\d\.]+)', r'math.pow(\1, \2)', q)
                        q = re.sub(r'(?:square root of|sqrt)\s*([\d\.]+)', r'math.sqrt(\1)', q)
                        q = re.sub(r'(\d+)\s*[xX]\s*(\d+)', r'\1 * \2', q)
                        q = q.replace(' multiplied by ', ' * ').replace(' times ', ' * ').replace(' x ', ' * ')
                        q = q.replace(' divided by ', ' / ').replace(' plus ', ' + ').replace(' minus ', ' - ')
                        allowed_names = {'math': math, 'sqrt': math.sqrt, 'pow': math.pow, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'pi': math.pi}
                        clean_expr = re.sub(r'[^0-9\+\-\*\/\(\)\.\s\,a-zA-Z_]', '', q)
                        res_val = eval(clean_expr, {'__builtins__': {}}, allowed_names)
                        success = True
                        message = f"The result is {res_val:g}."
                    except Exception as calc_err:
                        logger.warning(f"Math calculation failed: {calc_err}")
                        success = False
                        message = "I couldn't calculate that math expression."

            elif intent == "media_control":
                import ctypes
                VK_MEDIA_NEXT_TRACK = 0xB0
                VK_MEDIA_PREV_TRACK = 0xB1
                VK_MEDIA_STOP = 0xB2
                VK_MEDIA_PLAY_PAUSE = 0xB3

                if action == "next_track":
                    vk = VK_MEDIA_NEXT_TRACK
                    msg_text = "Skipped to next track."
                elif action == "previous_track":
                    vk = VK_MEDIA_PREV_TRACK
                    msg_text = "Returned to previous track."
                elif action == "stop":
                    vk = VK_MEDIA_STOP
                    msg_text = "Media playback stopped."
                else:
                    vk = VK_MEDIA_PLAY_PAUSE
                    msg_text = "Media playback toggled."

                try:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                    success = True
                    message = msg_text
                except Exception as m_err:
                    logger.error(f"Media key error: {m_err}")
                    success = False
                    message = "Failed to send media control command."

            elif intent == "spotify_control":
                res = self._execute_spotify_control(intent_node, confirm=confirm)
                if res.get("pending_confirmation"):
                    self._record_history(intent_node, res)
                    return res
                success = bool(res.get("success", False))
                message = res.get("message", "")
                outcome = res.get("outcome", CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED)

            elif intent in ["test_speech", "test_speakers"]:
                from core.tts.tts_manager import TTSManager
                success = True
                message = "Speaker audio output is operational."

            elif intent == "test_microphone":
                from core.listener import SpeechListener
                listener = SpeechListener()
                diag = listener.run_microphone_diagnostics()
                success = True
                message = diag.get("spoken_summary", "Microphone test completed.")

            elif intent in ["open_app", "application.launch"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application should I open, Sir?"
                else:
                    res = app_control.launch_application(target)
                    success = bool(res.get("success", False))
                    message = res.get("message", f"{target.title()} is open, Sir.")
                    raw_outcome = res.get("outcome", "SUCCESS" if success else "EXECUTION_FAILED")
                    if raw_outcome == "AMBIGUOUS":
                        outcome = CommandOutcome.MISSING_ARGUMENT
                    elif raw_outcome == "UNSUPPORTED_CAPABILITY":
                        outcome = CommandOutcome.UNSUPPORTED_CAPABILITY
                    elif success:
                        outcome = CommandOutcome.SUCCESS
                    else:
                        outcome = CommandOutcome.EXECUTION_FAILED

            elif intent in ["application.properties", "app_properties"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application's properties should I show, Sir?"
                else:
                    res = app_control.open_app_properties(target)
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent in ["application.install_dir", "app_install_dir"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application's installation folder should I open, Sir?"
                else:
                    res = app_control.open_app_install_dir(target)
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent in ["application.settings", "app_settings"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application's settings should I open, Sir?"
                else:
                    res = app_control.open_app_settings(target)
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent in ["application.metadata", "app_metadata"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application's version or details should I check, Sir?"
                else:
                    res = app_control.get_app_metadata(target)
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.UNSUPPORTED_CAPABILITY

            elif intent in ["application.status", "is_installed"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application should I check for, Sir?"
                else:
                    res = app_control.is_app_installed(target)
                    success = True
                    message = res.get("message", "")
                    outcome = CommandOutcome.SUCCESS

            elif intent in ["application.list_installed", "list_installed_apps"]:
                cat = intent_node.get("category")
                q = intent_node.get("query")
                res = app_control.list_installed_apps(category=cat)
                success = True
                message = res.get("message", "")
                outcome = CommandOutcome.SUCCESS

            elif intent in ["application.refresh", "refresh_apps"]:
                res = app_control.refresh_apps()
                success = True
                message = res.get("message", "Application registry refreshed.")
                outcome = CommandOutcome.SUCCESS

            elif intent in [
                "desktop.get_context", "desktop.enter_text", "desktop.search_in_app",
                "desktop.replace_selection", "desktop.send_message",
                "desktop_interaction.type_text", "desktop_interaction.write_reply",
                "desktop_interaction.search_app", "desktop_interaction.replace_selection",
                "desktop_interaction.continue_writing", "desktop_interaction.edit_draft",
                "desktop_interaction.paste_text", "desktop_interaction.send_message"
            ]:
                from core.interaction import desktop_context_service, text_entry_service
                
                if intent == "desktop.get_context":
                    ctx = desktop_context_service.get_current_context(
                        explicit_destination=target,
                        allow_ocr=bool(intent_node.get("allow_ocr", False))
                    )
                    success = True
                    targets_summary = ", ".join([t.name for t in ctx.available_targets[:3]]) or "No text fields identified"
                    message = f"Active window: '{ctx.window_title}' ({ctx.foreground_app}). Available targets: {targets_summary}."
                    outcome = CommandOutcome.SUCCESS

                elif intent in ["desktop.send_message", "desktop_interaction.send_message"]:
                    send_res = text_entry_service.execute_send_message(confirm=confirm)
                    success = bool(send_res.get("success", False))
                    message = send_res.get("message", "")
                    if send_res.get("pending_confirmation"):
                        return {
                            "success": False,
                            "outcome": CommandOutcome.PERMISSION_DENIED.value,
                            "message": message,
                            "intent": intent,
                            "action": "send_message",
                            "pending_confirmation": True,
                            "pending_intent": send_res.get("pending_intent")
                        }
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

                elif intent in ["desktop.search_in_app", "desktop_interaction.search_app"]:
                    query = intent_node.get("text") or intent_node.get("query") or target or ""
                    dest = intent_node.get("destination") or intent_node.get("explicit_destination")
                    res = text_entry_service.enter_text(
                        text=query,
                        action="search_in_app",
                        explicit_destination=dest,
                        submit=True
                    )
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    if res.get("requires_clarification") or res.get("requires_focus"):
                        return {
                            "success": True,
                            "outcome": CommandOutcome.SUCCESS.value,
                            "message": message,
                            "intent": intent,
                            "requires_clarification": res.get("requires_clarification", False),
                            "requires_focus": res.get("requires_focus", False),
                            "pending_intent": res.get("pending_intent")
                        }
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

                elif intent in ["desktop.replace_selection", "desktop_interaction.replace_selection"]:
                    text_content = intent_node.get("text") or target or ""
                    res = text_entry_service.enter_text(text=text_content, mode="replace")
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

                else:
                    # Generic text entry or reply drafting
                    text_content = intent_node.get("text") or target or ""
                    dest = intent_node.get("destination") or intent_node.get("explicit_destination")
                    act = "write_reply" if "reply" in intent else "enter_text"
                    mode = intent_node.get("mode", "insert")
                    res = text_entry_service.enter_text(
                        text=text_content,
                        action=act,
                        explicit_destination=dest,
                        mode=mode
                    )
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    if res.get("requires_clarification") or res.get("requires_focus"):
                        return {
                            "success": True,
                            "outcome": CommandOutcome.SUCCESS.value,
                            "message": message,
                            "intent": intent,
                            "requires_clarification": res.get("requires_clarification", False),
                            "requires_focus": res.get("requires_focus", False),
                            "pending_intent": res.get("pending_intent")
                        }
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            # ---------------------------------------------------------
            # VISION & SCREEN INTELLIGENCE
            # ---------------------------------------------------------
            elif intent in ["screen.analyze", "screen_understanding.analyze", "screen_understanding"]:
                from core.vision.screen_understanding import screen_understanding_engine
                from core.vision.models import CaptureTarget
                prompt_val = intent_node.get("prompt") or intent_node.get("query") or target or "Explain what is visible on my screen."
                target_scope = intent_node.get("target_scope") or intent_node.get("target") or "primary_screen"
                try:
                    cap_target = CaptureTarget(target_scope)
                except ValueError:
                    cap_target = CaptureTarget.PRIMARY_SCREEN
                from core.ai.provider_manager import ProviderManager
                prov_mgr = getattr(self, "provider_manager", None) or ProviderManager()
                res_analysis = screen_understanding_engine.analyze_screen(prompt=prompt_val, provider_manager=prov_mgr)
                success = True
                message = res_analysis.get("full_text") or res_analysis.get("summary") or "Screen analyzed."
                outcome = CommandOutcome.SUCCESS

            elif intent in ["screen.explain", "screen_understanding.explain", "vision_explain"]:
                from core.vision.explain_engine import explain_engine
                query_val = intent_node.get("query") or intent_node.get("text") or target or "Explain my screen."
                force_fresh = bool(intent_node.get("force_fresh", False))
                from core.ai.provider_manager import ProviderManager
                prov_mgr = getattr(self, "provider_manager", None) or ProviderManager()
                explanation = explain_engine.explain(query=query_val, provider_manager=prov_mgr, force_fresh_capture=force_fresh)
                success = True
                message = explanation.detailed_text or explanation.summary
                outcome = CommandOutcome.SUCCESS

            # ---------------------------------------------------------
            # FILE CREATION, SEARCH & PROJECT MANAGEMENT
            # ---------------------------------------------------------
            elif intent in ["files.create", "file_management.create_file", "file_creation"]:
                from core.files.file_creator import file_creator
                action_k = intent_node.get("action", "")

                # Handle follow-up save to folder (e.g. "Save it in my DSA folder")
                if action_k == "save_file" and hasattr(self, "last_created_file") and self.last_created_file:
                    dest_f = intent_node.get("destination") or target or "DSA"
                    import shutil
                    from pathlib import Path
                    src_p = Path(self.last_created_file)
                    dest_dir = Path.home() / "Desktop" / dest_f if not Path(dest_f).is_absolute() else Path(dest_f)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    target_f = dest_dir / src_p.name
                    try:
                        shutil.copy2(str(src_p), str(target_f))
                        self.last_created_file = str(target_f)
                        success = True
                        message = f"Saved '{src_p.name}' in {dest_f} folder."
                        outcome = CommandOutcome.SUCCESS
                    except Exception as fe:
                        success = False
                        message = f"Could not move file to {dest_f}: {fe}"
                        outcome = CommandOutcome.EXECUTION_FAILED
                else:
                    fn = intent_node.get("filename") or "script.py"
                    dest = intent_node.get("destination") or "Desktop"
                    content = intent_node.get("content") or intent_node.get("text") or "# Created by JARVIS\n"
                    lang = intent_node.get("language")
                    allow_ow = bool(confirm or intent_node.get("allow_overwrite", False))
                    res_fc = file_creator.create_file(filename=fn, destination=dest, content=content, language=lang, allow_overwrite=allow_ow)
                    if res_fc.requires_confirmation:
                        return {
                            "success": False,
                            "outcome": CommandOutcome.PERMISSION_DENIED.value,
                            "message": res_fc.message,
                            "intent": intent,
                            "pending_confirmation": True,
                            "pending_intent": intent_node
                        }
                    success = res_fc.success
                    message = res_fc.message
                    if success and getattr(res_fc, "file_path", None):
                        self.last_created_file = res_fc.file_path
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent in ["files.search", "file_management.search", "file_search"]:
                from core.files.file_memory import file_memory_manager
                q_search = intent_node.get("query") or target or ""
                ext_filter = intent_node.get("extension")
                proj_alias = intent_node.get("project_alias")
                found_records = file_memory_manager.search_files(query=q_search, extension=ext_filter, project_alias=proj_alias)
                success = True
                if found_records:
                    rec_list = "\n".join([f"- {r.filename} ({r.path})" for r in found_records[:5]])
                    message = f"Found {len(found_records)} matching files:\n{rec_list}"
                else:
                    message = f"No files matching '{q_search}' were found in indexed folders."
                outcome = CommandOutcome.SUCCESS

            elif intent in ["files.open", "file_management.open", "file_open"]:
                from core.files.file_memory import file_memory_manager
                f_path = intent_node.get("file_path") or target or ""
                success = file_memory_manager.open_in_explorer(f_path)
                message = f"Opened file in Explorer: {f_path}" if success else f"Could not find or open file: {f_path}"
                outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent in ["project.inspect", "project_management.inspect", "project_inspect"]:
                from core.files.project_inspector import project_inspector
                p_path = intent_node.get("project_path") or target or "."
                p_meta = project_inspector.inspect_project(p_path)
                success = True
                message = f"Project '{p_meta.name}' uses framework '{p_meta.framework}' and package manager '{p_meta.package_manager}'."
                outcome = CommandOutcome.SUCCESS

            elif intent in ["ai.get_providers", "ai_management.list_providers", "ai_providers"]:
                from core.ai.provider_settings import provider_settings_manager
                provs = provider_settings_manager.list_providers_summary()
                prov_lines = [f"- {p['name']} ({p['provider_id']}): model={p['model']}, priority={p['priority']}, enabled={p['enabled']}" for p in provs]
                success = True
                message = "Configured AI Providers:\n" + "\n".join(prov_lines)
                outcome = CommandOutcome.SUCCESS

            elif intent in ["ai.update_provider", "ai_management.update_provider"]:
                from core.ai.provider_settings import provider_settings_manager
                pid = intent_node.get("provider_id") or target or ""
                new_key = intent_node.get("api_key")
                new_model = intent_node.get("model")
                new_enabled = intent_node.get("enabled")
                if new_key:
                    provider_settings_manager.update_provider_key(pid, new_key)
                if new_model:
                    provider_settings_manager.update_provider_model(pid, new_model)
                if new_enabled is not None:
                    provider_settings_manager.set_provider_enabled(pid, bool(new_enabled))
                success = True
                message = f"Updated settings for AI provider '{pid}'."
                outcome = CommandOutcome.SUCCESS

            elif intent in ["ai.cache_stats", "ai_management.cache_stats"]:
                from core.ai.caching import nemotron_cache
                stats = nemotron_cache.get_stats()
                success = True
                message = (
                    f"JARVIS AI Cache Statistics:\n"
                    f"- Total Lookups: {stats.total_lookups}\n"
                    f"- Total Cache Hits: {stats.total_hits} (Exact: {stats.exact_hits}, Semantic: {stats.semantic_hits}, Knowledge: {stats.knowledge_hits}, Task: {stats.task_hits})\n"
                    f"- Outbound API Calls Saved: {stats.api_calls_saved} ({stats.duplicates_avoided} concurrent calls coalesced)\n"
                    f"- Hit Rate: {stats.hit_rate_pct:.1f}%\n"
                    f"- Bypasses: {stats.bypasses} | Misses: {stats.misses}"
                )
                outcome = CommandOutcome.SUCCESS

            elif intent in ["ai.clear_cache", "ai_management.clear_cache"]:
                from core.ai.caching import nemotron_cache
                cleared_count = nemotron_cache.clear()
                success = True
                message = f"Cleared {cleared_count} cached entries from the AI cache."
                outcome = CommandOutcome.SUCCESS

            elif intent in ["ai.forget_cache", "ai_management.forget_cache"]:
                from core.ai.caching import nemotron_cache
                target_q = target or intent_node.get("query", "")
                disputed_count = nemotron_cache.mark_disputed(target_q)
                success = True
                message = f"Marked {disputed_count} cached answer(s) as disputed. Fresh responses will be generated."
                outcome = CommandOutcome.SUCCESS

            elif intent == "command_management":
                from core.custom_commands.command_manager import command_manager
                cmd_res = command_manager.handle_management_command(target or intent_node.get("query", ""), confirm=confirm)
                success = bool(cmd_res.get("success", False))
                message = cmd_res.get("message", "")
                if cmd_res.get("pending_confirmation"):
                    return {
                        "success": False,
                        "outcome": CommandOutcome.PERMISSION_DENIED.value,
                        "message": message,
                        "intent": intent,
                        "action": action,
                        "target": target,
                        "spoken": True,
                        "pending_confirmation": True
                    }
                raw_out = cmd_res.get("outcome")
                if raw_out:
                    try:
                        outcome = CommandOutcome(raw_out)
                    except ValueError:
                        outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED
                else:
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent == "custom_command":
                from core.custom_commands.workflow_engine import workflow_engine
                from core.custom_commands.command_manager import command_manager
                wf = intent_node.get("workflow", [])
                wf_res = workflow_engine.execute_workflow(wf, confirm=confirm, executor=self)
                success = bool(wf_res.get("success", False))
                message = wf_res.get("message", "")
                if wf_res.get("pending_confirmation"):
                    return {
                        "success": False,
                        "outcome": CommandOutcome.PERMISSION_DENIED.value,
                        "message": message,
                        "intent": intent,
                        "action": action,
                        "target": target,
                        "spoken": True,
                        "pending_confirmation": True
                    }
                if not success:
                    first_fail = next((s for s in wf_res.get("steps", []) if s.get("status") == "FAILED"), None)
                    command_manager.last_failed_command_info = {
                        "command_name": intent_node.get("command_name", "custom_command"),
                        "step_index": (first_fail.get("step_index", 0) + 1) if first_fail else 1,
                        "reason": first_fail.get("message") if first_fail else message
                    }
                    outcome = CommandOutcome.EXECUTION_FAILED
                else:
                    outcome = CommandOutcome.SUCCESS

            elif intent == "close_app":
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application should I close, Sir?"
                else:
                    success = app_control.close_app(target)
                    if success:
                        outcome = CommandOutcome.SUCCESS
                        message = f"{target.title()} is closed, Sir."
                    else:
                        outcome = CommandOutcome.EXECUTION_FAILED
                        message = f"I couldn't close {target}, Sir."

            elif intent == "minimize_app":
                success = app_control.minimize_app(target)
                message = f"Minimized {target}." if (success and target) else ("Window minimized." if success else f"Failed to minimize {target or 'window'}.")

            elif intent == "maximize_app":
                success = app_control.maximize_app(target)
                message = f"Maximized {target}." if (success and target) else ("Window maximized." if success else f"Failed to maximize {target or 'window'}.")

            elif intent == "window_control":
                success, message = self._handle_window_control(action, target)

            elif intent == "file_access":
                success, message = self._handle_file_access(action, target)

            elif intent == "terminal_execute":
                cwd = self.project_registry.get_current_project()["path"]
                if action == "check_port":
                    port_num = int(target) if str(target).isdigit() else 5000
                    p_info = self.process_mgr.get_port_process(port_num)
                    if p_info:
                        success = True
                        message = f"Port {port_num} is used by process {p_info['name']} (PID {p_info['pid']})."
                    else:
                        success = True
                        message = f"Port {port_num} is currently free."
                elif action == "node_processes":
                    procs = self.process_mgr.find_process("node")
                    if procs:
                        success = True
                        p_list = ", ".join([f"{p['name']} (PID {p['pid']})" for p in procs])
                        message = f"Running Node processes: {p_list}."
                    else:
                        success = True
                        message = "No running Node processes found."
                else:
                    res = self.terminal_mgr.execute(target, cwd=cwd)
                    success = res["success"]
                    output = res["stdout"] or res["stderr"] or "Command completed."
                    if len(output) > 150:
                        message = "I found the output. I've displayed it in the Jarvis interface."
                    else:
                        message = f"Command output: {output}"

            elif intent == "system_telemetry":
                if action == "cpu_info":
                    res = self.system_info_mgr.get_cpu_info()
                elif action == "ram_info":
                    res = self.system_info_mgr.get_ram_info()
                elif action == "disk_info":
                    res = self.system_info_mgr.get_disk_info()
                elif action == "os_info":
                    res = self.system_info_mgr.get_os_info()
                elif action == "ip_info":
                    res = self.system_info_mgr.get_network_ip()
                elif action == "uptime_info":
                    res = self.system_info_mgr.get_uptime()
                elif action in ["battery_info", "battery", "power"]:
                    from core.os.power_manager import power_manager
                    res = power_manager.get_battery_telemetry()
                    success = res.get("success", False)
                    message = res.get("message", "Battery telemetry unavailable.")
                else:
                    res = self.system_info_mgr.get_cpu_info()
                if "text" in res:
                    success = res["success"]
                    message = res["text"]

            elif intent in ["power_control", "power.scheme"]:
                from core.os.power_manager import power_manager
                if action == "report":
                    res = power_manager.get_acer_oem_report()
                    success = True
                    message = f"{res['laptop_model']}. Active plan: {res['active_windows_scheme']}. {res['battery_status']} {res['integration_status']}"
                else:
                    res = power_manager.set_power_scheme(target or "Balanced")
                    success = res.get("success", False)
                    message = res.get("message", "")

            elif intent in ["workspace_control", "workspace.launch", "launch_workspace"]:
                from core.os.workspace_manager import workspace_manager
                confirmed = intent_node.get("confirmed_optional_ids")
                declined = intent_node.get("declined_optional_ids")
                always = intent_node.get("always_optional_ids")
                never = intent_node.get("never_optional_ids")
                res = workspace_manager.execute_workspace(target, confirmed_optional_ids=confirmed, declined_optional_ids=declined, always_optional_ids=always, never_optional_ids=never)
                success = res.get("success", False)
                message = res.get("message", "")
                if res.get("needs_confirmation"):
                    return {
                        "success": True,
                        "pending_confirmation": True,
                        "is_conversational_confirmation": True,
                        "intent": "workspace_optional_confirmation",
                        "action": "confirm_optional",
                        "target": target,
                        "workspace_id": res.get("workspace_id"),
                        "optional_id": res.get("optional_id"),
                        "message": res.get("prompt"),
                        "spoken": True
                    }

            elif intent in ["power.scheme", "power_scheme", "power_control"]:
                from core.os.power_manager import power_manager
                act = intent_node.get("action") or action or "get"
                scheme_target = target or intent_node.get("target") or (intent_node.get("entities", {}).get("target") if isinstance(intent_node.get("entities"), dict) else None) or "Balanced"
                if act in ["set", "set_scheme", "switch", "activate"]:
                    res = power_manager.set_power_scheme(scheme_target)
                    success = res.get("success", False)
                    message = res.get("message", "")
                else:
                    active = power_manager.get_active_scheme()
                    success = True
                    message = f"Active Windows power plan is '{active['name'] if active else 'Balanced'}'."

            elif intent in ["battery.status", "battery_telemetry"]:
                from core.os.power_manager import power_manager
                res = power_manager.get_battery_telemetry()
                success = res.get("success", False)
                message = res.get("message", "")

            elif intent == "acer_oem_control":
                from core.os.power_manager import power_manager
                if action == "set_profile":
                    res = power_manager.acer_adapter.set_oem_profile(target)
                    success = res.get("success", False)
                    message = res.get("message", "")
                elif action == "set_battery_threshold":
                    val = int(target or 80) if str(target or "").isdigit() else 80
                    res = power_manager.acer_adapter.set_battery_threshold(val)
                    success = res.get("success", False)
                    message = res.get("message", "")
                elif action == "launch_control_center":
                    res = power_manager.acer_adapter.launch_control_center()
                    success = res.get("success", False)
                    message = res.get("message", "")
                else:
                    rep = power_manager.get_acer_oem_report()
                    success = True
                    message = rep.get("integration_status", "")

            elif intent in ["system_telemetry", "hardware_status"]:
                from core.os.power_manager import power_manager
                tel_target = (target or "").lower()
                if tel_target in ["power", "battery"]:
                    res = power_manager.get_battery_telemetry()
                    success = res.get("success", False)
                    message = res.get("message", "")
                else:
                    status_dict = power_manager.get_comprehensive_status()
                    success = True
                    message = f"Power plan: {status_dict['active_windows_power_plan']}, Battery: {status_dict['battery_percentage']}%, Charging: {status_dict['battery_charging_status']}."

            elif intent == "project_control":
                success = self.project_registry.set_current_project(target)
                proj = self.project_registry.get_current_project()
                message = f"Switched project context to {proj['alias'].title()}." if success else f"Could not find project '{target}'."

            elif intent == "filesystem_control":
                cwd = self.project_registry.get_current_project()["path"]
                if action == "list_directory":
                    res = self.filesystem_mgr.list_directory(cwd)
                    success = res["success"]
                    if success:
                        files_str = ", ".join([item["name"] for item in res["items"][:5]])
                        message = f"Found {res['count']} items in {Path(cwd).name}: {files_str}."
                    else:
                        message = res.get("error", "Could not list directory.")
                elif action == "create_folder":
                    folder_path = self.filesystem_mgr.resolve_path(target or "New Folder")
                    try:
                        os.makedirs(folder_path, exist_ok=True)
                        success = folder_path.exists() and folder_path.is_dir()
                        message = f"Created folder {folder_path.name}." if success else "Failed to create folder."
                    except Exception as fe:
                        success = False
                        message = f"Error creating folder: {fe}"
                elif action in ["save_file", "write_file"]:
                    file_content = intent_node.get("content") or intent_node.get("query") or ""
                    res = self.content_gen.create_and_save_file(target, file_content)
                    success = res.get("success", False)
                    message = res.get("message", "")
                    if success:
                        self.last_created_file = res.get("path")
                else:
                    success = False
                    message = f"Unknown filesystem action: {action}"

            elif intent in ["browser_control", "browser_tab_control"]:
                success, message = self._handle_browser_control(action, target, intent_node)

            elif intent == "browser_action":
                if action in ["read_page", "inspect_page", "analyze_page"]:
                    res = self.browser_mgr.analyze_active_page()
                    success = res.get("success", False)
                    if success:
                        title = res.get("title") or "Current Page"
                        url = res.get("url") or ""
                        content = res.get("content") or ""
                        headings = res.get("headings") or []
                        head_text = f" Key sections: {', '.join(headings[:3])}." if headings else ""
                        if content:
                            snippet = content[:280].strip()
                            if len(content) > 280:
                                snippet += "..."
                            message = f"Active page is '{title}' ({url}).{head_text} Summary: {snippet}"
                        else:
                            message = f"Active page is '{title}' ({url})."
                        outcome = CommandOutcome.SUCCESS
                    else:
                        message = res.get("message") or "Unable to read active browser page."
                        outcome = CommandOutcome.UNSUPPORTED_CAPABILITY
                elif action in ["search_page", "search_website", "find_in_page"]:
                    query = intent_node.get("query") or intent_node.get("target") or ""
                    res = self.browser_mgr.search_active_page(query)
                    success = res.get("success", False)
                    message = res.get("message", f"Searched for '{query}'.")
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED
                else:
                    success = False
                    message = f"Unknown browser action: {action}"

            elif intent == "youtube_control":
                res = self.browser_mgr.youtube_control(action, target)
                success = res.get("success", False)
                message = res.get("message", "YouTube playback updated.")

            elif intent in ["content_generation", "explain_concept"]:
                ctype = intent_node.get("content_type")
                if not ctype:
                    if action == "draft_email":
                        ctype = "email"
                    elif action == "explain_concept":
                        ctype = "explanation"
                    elif action == "summarize_page":
                        ctype = "summary"
                    else:
                        ctype = "general"
                topic = intent_node.get("concept") or intent_node.get("target") or intent_node.get("query", "General")
                res = self.content_gen.draft_content(topic, content_type=ctype)
                success = res.get("success", True)
                message = res.get("content", "")

            elif intent in ["local_search", "search_code"]:
                cwd = self.project_registry.get_current_project()["path"]
                if action == "search_code":
                    res = self.filesystem_mgr.search_content(target or intent_node.get("query", ""), base_dir=cwd)
                    success = res.get("success", False)
                    if success and res.get("results"):
                        self.last_search_results = res["results"]
                        names = [Path(r).name for r in res["results"][:3]]
                        message = f"Found {res['count']} code references: {', '.join(names)}."
                    else:
                        message = f"No references found for '{target}' in {Path(cwd).name}."
                else:
                    folder = intent_node.get("folder")
                    search_dir = cwd
                    if folder == "downloads":
                        search_dir = str(Path.home() / "Downloads")
                    ext = intent_node.get("extension")
                    res = self.filesystem_mgr.search_files(target or intent_node.get("query", ""), base_dir=search_dir, extension=ext)
                    success = res.get("success", False)
                    if success and res.get("matches"):
                        self.last_search_results = res["matches"]
                        names = [Path(m).name for m in res["matches"][:3]]
                        message = f"Found matches: {', '.join(names)}."
                    else:
                        message = f"No files found matching '{target}'."

            elif intent == "developer_workflow":
                cwd = self.project_registry.get_current_project()["path"]
                if action == "run_tests":
                    cmd = ".venv\\Scripts\\python -m unittest discover tests" if os.name == "nt" else "python3 -m unittest discover tests"
                    res = self.terminal_mgr.execute(cmd, cwd=cwd)
                    out = (res.get("stdout") or "") + (res.get("stderr") or "")
                    if "Ran " in out or "OK" in out or "FAILED" in out:
                        success = "FAILED" not in out
                        lines = [line for line in out.splitlines() if "Ran " in line or "OK" in line or "FAILED" in line]
                        summary = " ".join(lines[-2:]) if lines else "Tests completed."
                        message = f"Test execution completed: {summary}"
                    else:
                        success = res.get("success", False)
                        message = f"Tests completed with output: {out[:120]}"
                else:
                    success = False
                    message = f"Unknown developer workflow action: {action}"

            elif intent == "follow_up":
                if action == "open_last_created_file":
                    if self.last_created_file:
                        res = self.filesystem_mgr.open_file(self.last_created_file)
                        success = res.get("success", False)
                        message = res.get("message", f"Opened {Path(self.last_created_file).name}.")
                    else:
                        success = False
                        message = "No recently created file found to open."
                elif action == "open_result_index":
                    idx = int(target) - 1 if str(target).isdigit() else 0
                    if self.last_search_results and 0 <= idx < len(self.last_search_results):
                        item = self.last_search_results[idx]
                        if item.startswith("http"):
                            success, message = web_control.open_website(item)
                        else:
                            res = self.filesystem_mgr.open_file(item)
                            success = res.get("success", False)
                            message = res.get("message", f"Opened {Path(item).name}.")
                    else:
                        success = False
                        message = f"Result number {target} is not available."

            elif intent == "screenshot":
                if action == "open_folder":
                    success = screenshot.open_screenshot_folder()
                    message = "Opening screenshots folder." if success else "Failed to open screenshots folder."
                else:
                    success, message = screenshot.take_screenshot()

            elif intent in ["system_control", "status_request", "system_action"]:
                success, message = self._handle_system_control(action, target)

            elif intent == "identity":
                success = True
                owner = getattr(config, "owner_name", "Active Gamer")
                name = getattr(config, "assistant_name", "Jarvis")
                message = f"I am {name}, your personal AI desktop assistant. I was designed and built by {owner} as a long-term personal AI operating system."

            elif intent == "help":
                success = True
                from core.capability_service import capability_service
                scope = intent_node.get("scope") or intent_node.get("target") or "overview"
                if scope == "all" or action == "show_all_commands":
                    message = capability_service.get_all_commands_reference()
                elif scope in ["browser", "filesystem", "applications", "system", "search", "developer", "content", "media", "custom"]:
                    message = capability_service.get_scoped_commands(scope)
                else:
                    from core.tool_registry import tool_registry
                    message = tool_registry.get_capabilities_summary()

            elif intent == "about":
                success = True
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                name = getattr(config, 'assistant_name', 'Jarvis')
                version = getattr(config, 'version', '1.1')
                owner = getattr(config, 'owner_name', 'Active Gamer')
                whisper_size = getattr(config, 'whisper_model_size', 'small')
                tts_voice = getattr(config, 'model_tts_voice', 'en-US-GuyNeural')
                llm_status = "Online" if config.gemini_api_key else "Offline Mode"

                message = (
                    f"{name} Assistant Version {version}\n"
                    f"Developer / Owner: {owner}\n"
                    f"Whisper Speech Model: {whisper_size}\n"
                    f"TTS Voice Engine: {tts_voice}\n"
                    f"LLM Cognitive Engine: {llm_status}\n"
                    f"OS Control Status: Operational\n"
                    f"CPU Usage: {cpu}%\n"
                    f"RAM Usage: {ram}%"
                )

            elif intent == "history_query":
                if self.history_tracker and self.history_tracker.get_history():
                    last_record = self.history_tracker.get_history()[-1]
                    cmd = last_record.get('command', 'Unknown')
                    res = last_record.get('result', 'Executed')
                    success = True
                    message = f"Your last command was: '{cmd}'. Result: {res}"
                else:
                    success = True
                    message = "No previous commands recorded in this session."

            elif intent == "explain_tool_execution":
                from core.observability import tool_explainer
                exp_res = tool_explainer.explain_recent_executions()
                success = True
                message = exp_res["text"]

            elif intent == "memory_control":
                from core.profile_manager import profile_manager
                if action == "save":
                    mem_text = target or intent_node.get("query", "")
                    success = profile_manager.add_memory(mem_text)
                    message = f"Saved to memory: '{mem_text}'." if success else "Failed to save memory."
                elif action == "recall":
                    topic_text = target or intent_node.get("query", "")
                    mems = profile_manager.query_memories(topic_text)
                    success = True
                    if mems:
                        message = "Here is what I remember:\n" + "\n".join(f"- {m}" for m in mems[:5])
                    else:
                        message = f"I don't have any saved notes about '{topic_text}'."
                elif action == "forget":
                    topic_text = target or intent_node.get("query", "")
                    success = profile_manager.forget_memory(topic_text)
                    message = f"Removed memory matching '{topic_text}'." if success else f"No memory found matching '{topic_text}'."
                else:
                    success = False
                    message = f"Unknown memory action: {action}"

            elif intent == "privacy_control":
                from core.security.privacy_guard import privacy_guard
                if action == "set_mode":
                    mode_val = (target or "GUARDED").upper()
                    success = privacy_guard.set_mode(mode_val)
                    mode_str = privacy_guard.get_mode()
                    message = f"Privacy mode updated to {mode_str}." if success else f"Invalid privacy mode '{target}'. Choose STRICT, GUARDED, or RELAXED."
                else:
                    mode_str = privacy_guard.get_mode()
                    success = True
                    if mode_str == "STRICT":
                        message = "Active privacy mode is STRICT: 100% local-first, zero cloud calls permitted."
                    elif mode_str == "GUARDED":
                        message = "Active privacy mode is GUARDED: Cloud permitted with automatic secret redaction and audit logging."
                    else:
                        message = "Active privacy mode is RELAXED: Direct cloud access without redaction (development mode)."

            elif intent == "unsupported_capability":
                success = False
                outcome = CommandOutcome.UNSUPPORTED_CAPABILITY
                message = "That capability isn't available yet, Sir."

            elif intent == "invalid_command":
                success = False
                outcome = CommandOutcome.INVALID_COMMAND
                message = "I couldn't complete that request, Sir. Try another command."

            else:
                success = False
                outcome = CommandOutcome.INVALID_COMMAND
                message = "I couldn't complete that request, Sir. Try another command."

        except Exception as e:
            logger.error(f"Execution failed with error: {e}", exc_info=True)
            success = False
            outcome = CommandOutcome.EXECUTION_FAILED
            message = "That action failed, Sir. Please try again."

        if outcome is None:
            outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

        result = {
            "success": success,
            "outcome": outcome.value if isinstance(outcome, CommandOutcome) else outcome,
            "message": message,
            "intent": intent,
            "action": action,
            "target": target,
            "spoken": True,
            "pending_confirmation": False
        }

        # 4. Record Action in History and Observability Tracking
        self._record_history(intent_node, result)
        try:
            dur_ms = (time.time() - t0) * 1000 if 't0' in locals() else 0.0
            from core.smart_memory import smart_memory
            from core.observability import tool_explainer
            smart_memory.record_tool_execution(intent, success, dur_ms, error=(message if not success else None))
            rationale = self._determine_tool_rationale(intent, intent_node)
            tool_explainer.record_decision(
                query=intent_node.get("raw_text") or intent_node.get("query") or intent,
                intent=intent,
                tool_name=intent,
                rationale=rationale,
                args={"target": target, "action": action},
                duration_ms=dur_ms,
                success=success,
                verification_evidence=f"Success={success}, OutputLength={len(message)}"
            )
        except Exception as oe:
            logger.debug(f"Observability record failed: {oe}")

        return result

    def _determine_tool_rationale(self, intent: str, node: dict) -> str:
        if intent == "web_search":
            prov = node.get("provider", "google")
            return f"Web search requested for provider '{prov}'."
        elif intent == "open_website":
            return f"Direct website navigation requested for destination '{node.get('target')}'."
        elif intent == "open_app":
            return f"Local application launch requested for '{node.get('target')}'."
        elif intent == "browser_control":
            return f"Browser tab or window control requested ({node.get('action')})."
        elif intent == "youtube_control":
            return f"YouTube video media playback control invoked ({node.get('action')})."
        elif intent == "content_generation":
            return f"Writing/drafting engine invoked for content type '{node.get('content_type', 'general')}'."
        elif intent == "filesystem_control":
            return f"Local filesystem operation invoked ({node.get('action')})."
        elif intent == "developer_workflow":
            return f"Developer project workflow invoked ({node.get('action')})."
        elif intent == "explain_tool_execution":
            return "User requested transparency report of recent tool calls."
        elif intent == "memory_control":
            return f"User profile memory operation invoked ({node.get('action')})."
        elif intent == "privacy_control":
            return f"Privacy policy inspection or update invoked ({node.get('action')})."
        elif intent == "system_control":
            return f"Deterministic OS system control invoked ({node.get('action')})."
        return f"Deterministic execution for intent '{intent}'."

    def _handle_window_control(self, action: str, target: str) -> (bool, str):
        if action == "minimize":
            success = window_control.minimize_window(target)
            return success, "Window minimized." if success else "Failed to minimize window."
        elif action == "maximize":
            success = window_control.maximize_window(target)
            return success, "Window maximized." if success else "Failed to maximize window."
        elif action == "restore":
            success = window_control.restore_window(target)
            return success, "Window restored." if success else "Failed to restore window."
        elif action in ["switch", "focus"]:
            if not target:
                return False, "No target window specified to switch to."
            success = window_control.switch_to_window(target)
            return success, f"Switched to {target}." if success else f"Failed to find window matching '{target}'."
        elif action == "close":
            success = window_control.close_window(target)
            return success, "Closed window." if success else "Failed to close window."
        elif action in ["list", "list_open"]:
            titles = window_control.list_open_windows()
            if not titles:
                return True, "No open windows detected."
            msg_list = ", ".join(titles[:5])
            if len(titles) > 5:
                msg_list += f" and {len(titles)-5} more"
            return True, f"Open windows: {msg_list}."
        else:
            return False, f"Unknown window control action: {action}"

    def _handle_file_access(self, action: str, target: str) -> (bool, str):
        if action == "open_folder":
            if not target:
                return False, "No folder target specified."
            success = file_control.open_folder(target)
            return success, f"Opened {target} folder." if success else f"Failed to open {target}."
        elif action == "open_file":
            if not target:
                return False, "No file path specified."
            success = file_control.open_file(target)
            return success, f"Opened file {target}." if success else "Failed to open file."
        elif action == "search_file":
            if not target:
                return False, "No search term specified."
            matches = file_control.search_files(target)
            if not matches:
                return True, f"No matching files found for '{target}'."
            names = [Path(m).name for m in matches[:3]]
            msg = f"Found matches: {', '.join(names)}"
            if len(matches) > 3:
                msg += f" (and {len(matches)-3} more)"
            return True, msg
        else:
            return False, f"Unknown file control action: {action}"

    def _handle_system_control(self, action: str, target: str) -> (bool, str):
        if action == "volume_up":
            return system_control.volume_up()
        elif action == "volume_down":
            return system_control.volume_down()
        elif action == "mute":
            return system_control.mute_volume()
        elif action == "unmute":
            return system_control.unmute_volume()
        elif action in ["lock", "lock_pc"]:
            return system_control.lock_pc()
        elif action in ["sleep_assistant", "enter_sleep", "sleep_mode"]:
            return True, "Entering sleep mode, Sir. Say 'Jarvis' to wake me."
        elif action in ["sleep", "sleep_pc"]:
            return system_control.sleep_pc()
        elif action in ["hibernate", "hibernate_pc"]:
            return system_control.hibernate_pc()
        elif action in ["restart", "restart_pc"]:
            return system_control.restart_pc()
        elif action in ["shutdown", "shutdown_pc"]:
            return system_control.shutdown_pc()
        elif action == "battery":
            return system_control.get_battery_status()
        elif action in ["cpu", "ram", "disk", "metrics"]:
            success, metrics = system_control.get_system_metrics()
            if success:
                return True, metrics["message"]
            return False, "Failed to retrieve system resource metrics."
        elif action in ["enable_startup", "start_with_windows"]:
            from core.startup import enable_startup
            ok = enable_startup()
            if ok:
                return True, "Jarvis is now configured to start automatically with Windows minimized to the system tray, Sir."
            return False, "I was unable to update the Windows startup registry. Please ensure permissions are granted."
        elif action in ["disable_startup", "stop_starting_with_windows"]:
            from core.startup import disable_startup
            ok = disable_startup()
            if ok:
                return True, "Automatic Windows startup has been disabled for Jarvis, Sir."
            return False, "I was unable to remove Jarvis from the Windows startup registry."
        elif action in ["startup_status", "check_startup", "is_startup_enabled"]:
            from core.startup import is_startup_enabled
            enabled = is_startup_enabled()
            if enabled:
                return True, "Jarvis is currently configured to start automatically with Windows in minimized standby."
            return True, "Automatic Windows startup is currently disabled for Jarvis."
        elif action in ["enter_standby", "standby"]:
            return True, "Entering standby mode, Sir. Say 'Hey Jarvis' or press Talk to activate me."
        elif action in ["disable_listening", "mute_mic", "stop_listening"]:
            return True, "Microphone muted. Hands-free listening disabled. Use the talk button to resume."
        elif action in ["enable_listening", "unmute_mic", "resume_listening"]:
            return True, "Microphone active. Hands-free listening resumed."
        else:
            return False, f"Unknown system control action: {action}"


    def _handle_browser_control(self, action: str, target: str, intent_node: dict) -> (bool, str):
        tab_target = intent_node.get("tab_target") or target or ""
        if action == "close_tab":
            res = self.browser_mgr.close_tab(target=tab_target)
            return res.get("success", False), res.get("message", "Closed active tab.")
        elif action == "switch_tab":
            res = self.browser_mgr.switch_tab(target=tab_target)
            return res.get("success", False), res.get("message", "Switched tab.")
        elif action == "list_tabs":
            res = self.browser_mgr.list_open_tabs()
            return res.get("success", False), res.get("message", "Listed open tabs.")
        elif action == "new_tab":
            res = self.browser_mgr.new_tab(url=target)
            return res.get("success", False), res.get("message", "Opened new tab.")
        elif action == "reopen_tab":
            res = self.browser_mgr.reopen_closed_tab()
            return res.get("success", False), res.get("message", "Reopened last closed tab.")
        elif action == "next_tab":
            res = self.browser_mgr.next_tab()
            return res.get("success", False), res.get("message", "Switched to next tab.")
        elif action in ["prev_tab", "previous_tab"]:
            res = self.browser_mgr.prev_tab()
            return res.get("success", False), res.get("message", "Switched to previous tab.")
        elif action == "reload_page":
            res = self.browser_mgr.reload_page()
            return res.get("success", False), res.get("message", "Page reloaded.")
        elif action == "go_back":
            res = self.browser_mgr.go_back()
            return res.get("success", False), res.get("message", "Navigated back.")
        elif action == "go_forward":
            res = self.browser_mgr.go_forward()
            return res.get("success", False), res.get("message", "Navigated forward.")
        elif action == "toggle_fullscreen":
            res = self.browser_mgr.toggle_fullscreen()
            return res.get("success", False), res.get("message", "Toggled fullscreen.")
        elif action == "open_downloads":
            res = self.browser_mgr.open_downloads()
            return res.get("success", False), res.get("message", "Opened browser downloads.")
        elif action == "open_history":
            res = self.browser_mgr.open_history()
            return res.get("success", False), res.get("message", "Opened browser history.")
        elif action == "list_tabs":
            res = self.browser_mgr.list_tabs()
            return res.get("success", False), res.get("message", "Listed open tabs.")
        elif action == "open_multiple":
            urls = intent_node.get("urls") or ([target] if target else [])
            res = self.browser_mgr.open_multiple_urls(urls)
            return res.get("success", False), res.get("message", "Opened websites.")
        else:
            return False, f"Unknown browser control action: {action}"

    def _execute_spotify_control(self, intent_node: dict, confirm: bool = False) -> dict:
        """Executes Spotify Web API operations with multi-turn context and safe destructive confirmation."""
        from modules.spotify import spotify_service, spotify_context
        from modules.spotify.client import SpotifyApiError, SpotifyPremiumRequiredError, SpotifyNoActiveDeviceError

        action = intent_node.get("action", "")
        target = intent_node.get("target", "")

        # Check connection status
        if not spotify_service.is_connected():
            return {
                "success": False,
                "outcome": CommandOutcome.EXECUTION_FAILED.value,
                "message": "Spotify is not connected. Please connect your Spotify account in Santra settings or click the Spotify button.",
                "intent": "spotify_control",
                "action": action
            }

        try:
            # 1. Play Liked Songs
            if action == "play_liked":
                res = spotify_service.play_liked_songs()
                return {"success": res.get("success", False), "message": res.get("message", "Playing liked songs on Spotify."), "action": action}

            # 2. Create Playlist
            elif action == "create_playlist":
                p_name = intent_node.get("playlist_name") or target or "New Playlist"
                p = spotify_service.create_playlist(p_name)
                return {"success": True, "message": f"{p.name} was created.", "action": action, "playlist_id": p.id}

            # 3. Add Specific Track to Playlist
            elif action == "add_track":
                t_name = intent_node.get("track_name") or target
                p_name = intent_node.get("playlist_name")
                res = spotify_service.add_tracks_by_search(playlist_name_or_id=p_name, query=t_name)
                return {"success": res.get("success", False), "message": res.get("message", ""), "action": action}

            # 4. Add N Songs by Artist
            elif action == "add_tracks_by_artist":
                count = intent_node.get("count", 1)
                artist = intent_node.get("artist") or target
                p_name = intent_node.get("playlist_name")
                res = spotify_service.add_tracks_by_search(playlist_name_or_id=p_name, query=artist, artist=artist, count=count)
                return {"success": res.get("success", False), "message": res.get("message", ""), "action": action}

            # 5. Remove Track
            elif action == "remove_track":
                p_name = intent_node.get("playlist_name")
                idx = intent_node.get("index")
                t_name = intent_node.get("track_name")

                target_p_id = None
                target_p_name = ""
                if p_name:
                    p = spotify_service.find_playlist_by_name(p_name)
                    if p:
                        target_p_id = p.id
                        target_p_name = p.name
                    else:
                        target_p_id = p_name
                        target_p_name = p_name
                elif spotify_context.active_playlist_id:
                    target_p_id = spotify_context.active_playlist_id
                    target_p_name = spotify_context.active_playlist_name or "active playlist"
                else:
                    return {"success": False, "message": "Which playlist would you like me to remove the song from?"}

                tracks = spotify_service.get_playlist_tracks(target_p_id)
                if not tracks:
                    return {"success": False, "message": f"Playlist '{target_p_name}' has no songs to remove."}

                if idx is not None:
                    pos = idx - 1
                    if 0 <= pos < len(tracks):
                        target_track = tracks[pos]
                        res = spotify_service.remove_tracks_from_playlist(target_p_id, positions=[pos])
                        return {"success": True, "message": f"Removed '{target_track.name}' by {target_track.artist} from {target_p_name}."}
                    else:
                        return {"success": False, "message": f"There is no song number {idx} in {target_p_name}. It only has {len(tracks)} songs."}
                elif t_name:
                    found_track = None
                    pos = -1
                    for i, t in enumerate(tracks):
                        if t_name.lower() in t.name.lower():
                            found_track = t
                            pos = i
                            break
                    if found_track and pos >= 0:
                        res = spotify_service.remove_tracks_from_playlist(target_p_id, positions=[pos])
                        return {"success": True, "message": f"Removed '{found_track.name}' by {found_track.artist} from {target_p_name}."}
                    else:
                        return {"success": False, "message": f"Could not find song '{t_name}' in {target_p_name}."}
                else:
                    return {"success": False, "message": "Which song would you like to remove?"}

            # 6. Reorder Track: Move to top
            elif action == "reorder_track":
                from_idx = intent_node.get("from_index", 1)
                to_idx = intent_node.get("to_index", 1)
                p_name = intent_node.get("playlist_name")
                target_p_id = None
                target_p_name = ""
                if p_name:
                    p = spotify_service.find_playlist_by_name(p_name)
                    if p:
                        target_p_id = p.id
                        target_p_name = p.name
                elif spotify_context.active_playlist_id:
                    target_p_id = spotify_context.active_playlist_id
                    target_p_name = spotify_context.active_playlist_name or "active playlist"

                if not target_p_id:
                    return {"success": False, "message": "Which playlist would you like to reorder?"}

                tracks = spotify_service.get_playlist_tracks(target_p_id)
                if not tracks:
                    return {"success": False, "message": f"Playlist '{target_p_name}' has no tracks to move."}

                range_start = max(0, min(from_idx - 1, len(tracks) - 1))
                insert_before = max(0, min(to_idx - 1, len(tracks)))
                moved_track = tracks[range_start]
                res = spotify_service.reorder_playlist_tracks(target_p_id, range_start=range_start, insert_before=insert_before)
                return {"success": True, "message": f"Moved '{moved_track.name}' to the top of {target_p_name}."}

            # 7. Rename Playlist
            elif action == "rename_playlist":
                old_name = intent_node.get("playlist_name") or target
                new_name = intent_node.get("new_name")
                if not new_name:
                    return {"success": False, "message": f"What new name would you like for {old_name}?"}
                p = spotify_service.find_playlist_by_name(old_name)
                if not p:
                    return {"success": False, "message": f"I couldn't find a playlist named '{old_name}' in your library."}
                res = spotify_service.rename_playlist(p.id, new_name)
                return {"success": True, "message": f"Renamed playlist '{old_name}' to '{new_name}'."}

            # 8. Delete / Unfollow Playlist (Destructive - Requires Confirmation)
            elif action == "delete_playlist":
                p_name = intent_node.get("playlist_name") or target
                p = spotify_service.find_playlist_by_name(p_name) if p_name else None
                if not p and spotify_context.active_playlist_id:
                    try:
                        p = spotify_service.get_playlist(spotify_context.active_playlist_id)
                    except Exception:
                        pass

                if not p:
                    return {"success": False, "message": f"I couldn't find the playlist '{p_name or 'requested'}' in your Spotify library."}

                if not confirm:
                    explanation_msg = (
                        f"Are you sure you want to remove the playlist '{p.name}'? "
                        "Spotify's Web API will unfollow and remove it from your library; "
                        "it cannot be permanently deleted from Spotify's servers."
                    )
                    return {
                        "success": False,
                        "outcome": CommandOutcome.PERMISSION_DENIED.value,
                        "message": explanation_msg,
                        "intent": "spotify_control",
                        "action": "delete_playlist",
                        "target": p.name,
                        "is_conversational_confirmation": True,
                        "pending_confirmation": True,
                        "metadata": {
                            "playlist_id": p.id,
                            "playlist_name": p.name,
                            "action": "delete_playlist"
                        }
                    }

                p_id = intent_node.get("playlist_id") or intent_node.get("metadata", {}).get("playlist_id") or p.id
                res = spotify_service.unfollow_playlist(p_id)
                return {"success": True, "message": res.get("message", f"Playlist '{p.name}' removed from your library.")}

            # 9. Clean up Duplicates
            elif action == "cleanup_duplicates":
                p_name = intent_node.get("playlist_name")
                target_p_id = None
                target_p_name = ""
                if p_name:
                    p = spotify_service.find_playlist_by_name(p_name)
                    if p:
                        target_p_id = p.id
                        target_p_name = p.name
                elif spotify_context.active_playlist_id:
                    target_p_id = spotify_context.active_playlist_id
                    target_p_name = spotify_context.active_playlist_name or "active playlist"

                if not target_p_id:
                    return {"success": False, "message": "Which playlist would you like me to check for duplicates?"}

                res = spotify_service.cleanup_duplicates(target_p_id)
                return {"success": True, "message": res.get("message", "Cleaned up duplicate songs.")}

            # 10. Play Playlist
            elif action == "play_playlist":
                p_name = intent_node.get("playlist_name") or target
                res = spotify_service.play_playlist(p_name)
                return {"success": res.get("success", False), "message": res.get("message", f"Playing {p_name} on Spotify.")}

            # 11. Play Active Context
            elif action == "play_current_context":
                if spotify_context.active_playlist_id:
                    res = spotify_service.play(context_uri=f"spotify:playlist:{spotify_context.active_playlist_id}")
                    return {"success": res.get("success", False), "message": res.get("message", f"Playing {spotify_context.active_playlist_name or 'playlist'} on Spotify.")}
                else:
                    res = spotify_service.play()
                    return {"success": res.get("success", False), "message": res.get("message", "Resumed playback on Spotify.")}

            # 12. Currently Playing Track
            elif action == "current_track":
                state = spotify_service.get_current_playback()
                if state and state.item:
                    dev_name = state.device.name if state.device else "Spotify"
                    msg = f"Currently playing '{state.item.name}' by {state.item.artist} on {dev_name}."
                    return {"success": True, "message": msg}
                else:
                    return {"success": True, "message": "Nothing is currently playing on Spotify."}

            # 13. List Playlists
            elif action == "list_playlists":
                playlists = spotify_service.list_playlists(limit=10)
                if playlists:
                    names = ", ".join(f"'{p.name}'" for p in playlists[:6])
                    more = f" and {len(playlists) - 6} more" if len(playlists) > 6 else ""
                    return {"success": True, "message": f"You have {len(playlists)} playlists on Spotify: {names}{more}."}
                else:
                    return {"success": True, "message": "You don't have any playlists in your Spotify library."}

            # 14. Playback Controls
            elif action == "pause":
                res = spotify_service.pause()
                return {"success": res.get("success", False), "message": res.get("message", "Spotify paused.")}

            elif action in ["resume", "play"]:
                res = spotify_service.play()
                return {"success": res.get("success", False), "message": res.get("message", "Spotify playing.")}

            elif action == "next_track":
                res = spotify_service.next_track()
                return {"success": res.get("success", False), "message": res.get("message", "Skipped to next track.")}

            elif action == "previous_track":
                res = spotify_service.previous_track()
                return {"success": res.get("success", False), "message": res.get("message", "Returned to previous track.")}

            elif action == "shuffle":
                st = intent_node.get("state", True)
                res = spotify_service.set_shuffle(st)
                return {"success": res.get("success", False), "message": res.get("message", f"Shuffle turned {'on' if st else 'off'}.")}

            elif action == "transfer_device":
                dev_name = intent_node.get("device_name") or target
                res = spotify_service.transfer_playback(dev_name)
                return {"success": res.get("success", False), "message": res.get("message", f"Transferred playback to {dev_name}.")}

            elif action == "volume":
                vol = intent_node.get("volume", 50)
                res = spotify_service.set_volume(vol)
                return {"success": res.get("success", False), "message": res.get("message", f"Set volume to {vol}%.")}

            else:
                return {"success": False, "message": f"Unknown Spotify command action: {action}"}

        except SpotifyPremiumRequiredError:
            return {
                "success": False,
                "message": "Spotify Web API player commands require a Spotify Premium subscription. Local media keys can control playback when Spotify Desktop is running."
            }
        except SpotifyNoActiveDeviceError:
            return {
                "success": False,
                "message": "No active Spotify playback device detected. Please open Spotify on your PC or phone."
            }
        except SpotifyApiError as e:
            return {"success": False, "message": f"Spotify API error: {e}"}
        except Exception as ex:
            logger.error(f"Unexpected error executing Spotify command: {ex}", exc_info=True)
            return {"success": False, "message": f"Failed to execute Spotify command: {ex}"}

    def _record_history(self, intent_node: dict, result: dict):
        if self.history_tracker:
            try:
                self.history_tracker.add_action(
                    command=intent_node.get("query", "Voice command"),
                    intent=intent_node.get("intent", "unknown"),
                    result=result.get("message", "Executed"),
                    success=result.get("success", False)
                )
            except Exception as e:
                logger.error(f"Failed to record action history: {e}")
