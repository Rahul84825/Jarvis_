"""Desktop Screen Capture Subsystem for JARVIS.

Supports capturing:
- Primary monitor
- All monitors (virtual desktop)
- Active foreground window
- Specified window by handle or title
- Selected rectangular screen region
- Custom image file input

Handles DPI scaling, multi-monitor coordinates, headless fallback,
and temporary capture file management.
"""

import os
import sys
import io
import time
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image, ImageDraw

from core.vision.models import CaptureTarget, ScreenRegion

logger = logging.getLogger("Jarvis.ScreenCapture")

TEMP_SCREENSHOT_DIR = Path(__file__).parent.parent.parent / "screenshots" / "temp"
TEMP_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class ScreenCaptureManager:
    """Manages secure on-demand screen captures with resource cleanup."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.temp_dir = temp_dir or TEMP_SCREENSHOT_DIR
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._last_capture_path: Optional[str] = None

    def capture(
        self,
        target: CaptureTarget = CaptureTarget.PRIMARY_SCREEN,
        region: Optional[ScreenRegion] = None,
        hwnd: Optional[int] = None,
        custom_image_path: Optional[str] = None
    ) -> Tuple[Optional[Image.Image], Optional[str]]:
        """Captures an image based on target scope and saves to a temporary path.
        Returns: (PIL.Image, file_path)
        """
        image: Optional[Image.Image] = None

        if target == CaptureTarget.CUSTOM_IMAGE and custom_image_path:
            p = Path(custom_image_path)
            if p.exists() and p.is_file():
                try:
                    image = Image.open(str(p)).convert("RGB")
                    return image, str(p)
                except Exception as e:
                    logger.error(f"Failed to open custom image '{custom_image_path}': {e}")
            else:
                logger.warning(f"Custom image path does not exist: {custom_image_path}")

        try:
            if target == CaptureTarget.ACTIVE_WINDOW:
                image = self._capture_active_window(hwnd=hwnd)
            elif target == CaptureTarget.SELECTED_WINDOW and hwnd:
                image = self._capture_window_by_hwnd(hwnd)
            elif target == CaptureTarget.REGION and region:
                image = self._capture_region(region)
            elif target == CaptureTarget.ALL_SCREENS:
                image = self._capture_all_screens()
            else:
                image = self._capture_primary_screen()

        except Exception as e:
            logger.warning(f"Native screen capture encountered error: {e}. Attempting fallback.")
            image = self._create_fallback_image(target, str(e))

        if image is None:
            image = self._create_fallback_image(target, "Desktop display unavailable")

        # Save temporary screenshot file
        ts = int(time.time() * 1000)
        filename = f"capture_{target.value}_{ts}.png"
        file_path = str(self.temp_dir / filename)
        try:
            image.save(file_path, format="PNG")
            self._last_capture_path = file_path
        except Exception as e:
            logger.error(f"Failed to save temporary screenshot: {e}")
            file_path = None

        return image, file_path

    @staticmethod
    def _run_in_attached_thread(func):
        """Executes func in a desktop-attached thread. If current thread cannot be attached
        (e.g. because it already owns GUI windows or hooks), runs func in a short-lived worker thread.
        """
        if sys.platform != "win32":
            return func()

        import ctypes
        import threading
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk and user32.SetThreadDesktop(hdesk):
            return func()

        # Current thread cannot attach (ERROR_BUSY); delegate to clean worker thread
        ret_box = [None]
        err_box = [None]

        def _worker():
            try:
                h = user32.OpenInputDesktop(0, False, 0x01FF)
                if h:
                    user32.SetThreadDesktop(h)
                ret_box[0] = func()
            except Exception as ex:
                err_box[0] = ex

        t = threading.Thread(target=_worker, name="DesktopCaptureWorker")
        t.start()
        t.join(timeout=8.0)

        if err_box[0]:
            raise err_box[0]
        return ret_box[0]

    def validate_image(self, img: Optional[Image.Image]) -> bool:
        """Public validator to verify a captured image is non-empty, decodable, and valid."""
        return self._validate_image(img)

    def _validate_image(self, img: Optional[Image.Image]) -> bool:
        """Validates that a captured image is non-empty, decodable, and has valid dimensions."""
        if img is None:
            return False
        if not hasattr(img, "size") or img.width < 10 or img.height < 10:
            return False
        return True

    def _capture_primary_screen(self) -> Image.Image:
        """Captures primary monitor display with multi-tier fallback."""
        def _do_grab():
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(all_screens=False)
                if self._validate_image(img):
                    return img
            except Exception as e:
                logger.debug(f"ImageGrab primary failed: {e}")

            try:
                import pyautogui
                img = pyautogui.screenshot()
                if self._validate_image(img):
                    return img
            except Exception as e:
                logger.debug(f"PyAutoGUI screenshot failed: {e}")

            return self._capture_via_win32_gdi()

        return self._run_in_attached_thread(_do_grab)

    def _capture_all_screens(self) -> Image.Image:
        """Captures complete virtual desktop across all connected monitors."""
        def _do_grab():
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(all_screens=True)
                if self._validate_image(img):
                    return img
            except Exception as e:
                logger.debug(f"ImageGrab all_screens failed: {e}")

            return self._capture_primary_screen()

        return self._run_in_attached_thread(_do_grab)

    def _capture_active_window(self, hwnd: Optional[int] = None) -> Image.Image:
        """Captures the foreground active application window."""
        def _do_grab():
            import win32gui
            target_hwnd = hwnd or win32gui.GetForegroundWindow()
            if not target_hwnd or not win32gui.IsWindow(target_hwnd):
                logger.info("No active foreground window found; falling back to primary screen.")
                return self._capture_primary_screen()
            return self._capture_window_by_hwnd(target_hwnd)

        return self._run_in_attached_thread(_do_grab)

    def _get_window_bounds(self, hwnd: int) -> Tuple[int, int, int, int]:
        """Gets accurate window bounding rectangle on Windows, using DWM when available."""
        import win32gui
        import ctypes
        from ctypes import wintypes

        # Try DwmGetWindowAttribute for accurate visual bounds (excluding invisible drop shadow)
        try:
            dwmapi = ctypes.windll.dwmapi
            rect = wintypes.RECT()
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            hr = dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect)
            )
            if hr == 0:
                x1, y1, x2, y2 = rect.left, rect.top, rect.right, rect.bottom
                if x2 > x1 and y2 > y1:
                    return x1, y1, x2, y2
        except Exception:
            pass

        # Fallback to standard GetWindowRect
        rect = win32gui.GetWindowRect(hwnd)
        return rect[0], rect[1], rect[2], rect[3]

    def _capture_window_by_hwnd(self, hwnd: int) -> Image.Image:
        """Captures a window by its Windows HWND handle with PrintWindow and bbox fallbacks."""
        def _do_grab():
            import win32gui
            import win32con

            if not win32gui.IsWindow(hwnd):
                logger.warning(f"Invalid HWND {hwnd}, falling back to primary screen.")
                return self._capture_primary_screen()

            # Check if window is minimized
            if win32gui.IsIconic(hwnd):
                title = win32gui.GetWindowText(hwnd) or f"HWND {hwnd}"
                logger.warning(f"Window '{title}' is minimized; cannot perform window-specific capture. Capturing primary screen.")
                return self._capture_primary_screen()

            x1, y1, x2, y2 = self._get_window_bounds(hwnd)
            w = max(10, x2 - x1)
            h = max(10, y2 - y1)

            # Method 1: PrintWindow API (captures window content directly via GDI even if partially occluded)
            try:
                pw_img = self._capture_window_via_printwindow(hwnd, w, h)
                if self._validate_image(pw_img):
                    return pw_img
            except Exception as e:
                logger.debug(f"PrintWindow capture failed for HWND {hwnd}: {e}")

            # Method 2: ImageGrab with multi-monitor bounding box
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
                if self._validate_image(img):
                    return img
            except Exception as e:
                logger.debug(f"ImageGrab bbox failed for HWND {hwnd}: {e}")

            # Method 3: Crop full desktop screenshot
            try:
                full = self._capture_all_screens()
                if full and x1 >= 0 and y1 >= 0 and x2 <= full.width and y2 <= full.height:
                    cropped = full.crop((x1, y1, x2, y2))
                    if self._validate_image(cropped):
                        return cropped
            except Exception:
                pass

            return self._capture_primary_screen()

        return self._run_in_attached_thread(_do_grab)

    def _capture_window_via_printwindow(self, hwnd: int, width: int, height: int) -> Optional[Image.Image]:
        """Low-level Windows PrintWindow capture via GDI."""
        import ctypes
        import win32gui
        import win32ui
        import win32con

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None

        mfc_dc = None
        save_dc = None
        save_bitmap = None

        try:
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(save_bitmap)

            # PW_RENDERFULLCONTENT = 2
            user32 = ctypes.windll.user32
            res = user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            if res != 1:
                # Fallback to standard PrintWindow (flag 0)
                res = user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)

            if res == 1:
                bmpinfo = save_bitmap.GetInfo()
                bmpstr = save_bitmap.GetBitmapBits(True)
                im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
                return im
            return None
        finally:
            if save_bitmap:
                try: win32gui.DeleteObject(save_bitmap.GetHandle())
                except Exception: pass
            if save_dc:
                try: save_dc.DeleteDC()
                except Exception: pass
            if mfc_dc:
                try: mfc_dc.DeleteDC()
                except Exception: pass
            if hwnd_dc:
                try: win32gui.ReleaseDC(hwnd, hwnd_dc)
                except Exception: pass

    def _capture_region(self, region: ScreenRegion) -> Image.Image:
        """Captures a specific bounding region (x, y, w, h)."""
        self._attach_thread_to_input_desktop()
        x1 = region.x
        y1 = region.y
        x2 = region.x + region.width
        y2 = region.y + region.height
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            if self._validate_image(img):
                return img
        except Exception:
            pass

        full = self._capture_primary_screen()
        if full and self._validate_image(full):
            return full.crop((max(0, x1), max(0, y1), min(full.width, x2), min(full.height, y2)))
        return full

    def _capture_via_win32_gdi(self) -> Image.Image:
        """Low-level Windows GDI BitBlt capture."""
        self._attach_thread_to_input_desktop()
        import win32gui
        import win32ui
        import win32con

        hdesktop = win32gui.GetDesktopWindow()
        rect = win32gui.GetWindowRect(hdesktop)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]

        desktop_dc = win32gui.GetWindowDC(hdesktop)
        if not desktop_dc:
            return self._create_fallback_image(CaptureTarget.PRIMARY_SCREEN, "Unable to get desktop DC")

        img_dc = None
        mem_dc = None
        screenshot = None

        try:
            img_dc = win32ui.CreateDCFromHandle(desktop_dc)
            mem_dc = img_dc.CreateCompatibleDC()
            screenshot = win32ui.CreateBitmap()
            screenshot.CreateCompatibleBitmap(img_dc, width, height)
            mem_dc.SelectObject(screenshot)

            mem_dc.BitBlt((0, 0), (width, height), img_dc, (0, 0), win32con.SRCCOPY)

            bmpinfo = screenshot.GetInfo()
            bmpstr = screenshot.GetBitmapBits(True)
            im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
            return im
        finally:
            if screenshot:
                try: win32gui.DeleteObject(screenshot.GetHandle())
                except Exception: pass
            if mem_dc:
                try: mem_dc.DeleteDC()
                except Exception: pass
            if img_dc:
                try: img_dc.DeleteDC()
                except Exception: pass
            if desktop_dc:
                try: win32gui.ReleaseDC(hdesktop, desktop_dc)
                except Exception: pass

    def _create_fallback_image(self, target: CaptureTarget, reason: str) -> Image.Image:
        """Creates a standardized placeholder image when display capture is inaccessible."""
        w, h = 1280, 720
        img = Image.new("RGB", (w, h), color=(15, 23, 42))  # Slate dark
        draw = ImageDraw.Draw(img)
        draw.rectangle([(20, 20), (w - 20, h - 20)], outline=(56, 189, 248), width=3)
        draw.text((40, 40), "JARVIS Screen Capture (Virtual Desktop Context)", fill=(240, 249, 255))
        draw.text((40, 70), f"Scope: {target.value.upper()}", fill=(147, 197, 253))
        draw.text((40, 100), f"Status: Active | Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}", fill=(148, 163, 184))
        draw.text((40, 130), f"Note: {reason}", fill=(251, 146, 60))
        return img

    def encode_image_base64(self, image: Image.Image, max_dim: int = 1280) -> str:
        """Resizes proportionally and encodes image to Base64 JPEG for multimodal AI models."""
        img = image.copy()
        w, h = img.size
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def cleanup_temp_screenshots(self, max_age_seconds: float = 3600):
        """Cleans up temporary screen capture artifacts older than max_age_seconds."""
        now = time.time()
        for f in self.temp_dir.glob("capture_*.png"):
            try:
                if now - f.stat().st_mtime > max_age_seconds:
                    f.unlink()
            except Exception as e:
                logger.debug(f"Failed to delete old capture {f}: {e}")


# Global singleton instance
screen_capture_manager = ScreenCaptureManager()

