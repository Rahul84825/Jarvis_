"""OCR Engine Subsystem for JARVIS Desktop Intelligence.

Provides zero-dependency Windows-native OCR using Windows.Media.Ocr (built into Windows 10/11)
with graceful fallback to pytesseract if installed.
Supports image preprocessing, confidence scoring, line extraction, and actionable diagnostics.
"""

import os
import sys
import time
import json
import logging
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from PIL import Image, ImageOps, ImageFilter

logger = logging.getLogger("Jarvis.OCREngine")


@dataclass
class OCRResult:
    """Normalized structured result of an OCR extraction pass."""
    text: str = ""
    lines: List[str] = field(default_factory=list)
    confidence: float = 0.0
    engine_used: str = "none"
    success: bool = False
    duration_ms: float = 0.0
    error: Optional[str] = None

    def has_meaningful_content(self, min_chars: int = 5) -> bool:
        """Determines whether extracted text contains real readable content."""
        clean = "".join(c for c in self.text if c.isalnum() or c.isspace()).strip()
        return len(clean) >= min_chars


class OCREngine:
    """Manages local OCR extraction with Windows.Media.Ocr native engine and pytesseract fallback."""

    def __init__(self):
        self._win_ocr_script_path: Optional[Path] = None
        self._is_windows_media_ocr_available: Optional[bool] = None
        self._ensure_powershell_script()

    def _ensure_powershell_script(self):
        """Pre-creates the reusable Windows.Media.Ocr PowerShell runner script."""
        script_dir = Path(__file__).parent / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        self._win_ocr_script_path = script_dir / "windows_media_ocr.ps1"

        script_content = r"""param([string]$ImagePath)
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    Add-Type -AssemblyName System.IO

    $asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
        $_.Name -eq 'AsTask' -and 
        $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
    }

    $fullPath = [System.IO.Path]::GetFullPath($ImagePath)

    [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

    $fileOp = [Windows.Storage.StorageFile]::GetFileFromPathAsync($fullPath)
    $fileTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Storage.StorageFile]).Invoke($null, @($fileOp))
    $file = $fileTask.GetAwaiter().GetResult()

    $streamOp = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
    $streamTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Storage.Streams.IRandomAccessStream]).Invoke($null, @($streamOp))
    $stream = $streamTask.GetAwaiter().GetResult()

    $decoderOp = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
    $decoderTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Graphics.Imaging.BitmapDecoder]).Invoke($null, @($decoderOp))
    $decoder = $decoderTask.GetAwaiter().GetResult()

    $softwareBitmapOp = $decoder.GetSoftwareBitmapAsync()
    $softwareBitmapTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Graphics.Imaging.SoftwareBitmap]).Invoke($null, @($softwareBitmapOp))
    $softwareBitmap = $softwareBitmapTask.GetAwaiter().GetResult()

    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $ocrEngine) {
        $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
    }
    if ($null -eq $ocrEngine) {
        Write-Output '{"error": "Windows.Media.Ocr engine unavailable for installed languages", "text_b64": "", "lines_b64": []}'
        exit 0
    }

    $ocrOp = $ocrEngine.RecognizeAsync($softwareBitmap)
    $ocrTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Media.Ocr.OcrResult]).Invoke($null, @($ocrOp))
    $ocrResult = $ocrTask.GetAwaiter().GetResult()

    $rawText = if ($null -ne $ocrResult.Text) { $ocrResult.Text } else { "" }
    $textB64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($rawText))
    $linesB64 = @($ocrResult.Lines | ForEach-Object { [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_.Text)) })

    $res = @{
        text_b64 = $textB64
        lines_b64 = $linesB64
        line_count = $linesB64.Count
    }
    $res | ConvertTo-Json -Compress
} catch {
    $errB64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_.Exception.Message))
    Write-Output "{`"error_b64`": `"$errB64`", `"text_b64`": `"`", `"lines_b64`": []}"
}
"""
        try:
            with open(self._win_ocr_script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
        except Exception as e:
            logger.error(f"Failed to create Windows OCR script: {e}")

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Applies light contrast enhancement and normalizes resolution for optimal OCR accuracy."""
        try:
            # Ensure RGB
            if image.mode != "RGB":
                img = image.convert("RGB")
            else:
                img = image.copy()

            # If image is very small, upscale proportionally to improve character recognition
            w, h = img.size
            if w < 600 or h < 300:
                scale = max(2.0, 800.0 / max(w, 1))
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

            return img
        except Exception as e:
            logger.debug(f"Image preprocessing fallback: {e}")
            return image

    def extract_text(self, image: Image.Image, timeout_sec: float = 8.0) -> OCRResult:
        """Performs OCR on the provided PIL Image using Windows.Media.Ocr or pytesseract."""
        t0 = time.time()

        if image is None or image.width < 5 or image.height < 5:
            return OCRResult(
                error="Invalid or empty image provided for OCR",
                engine_used="none",
                success=False
            )

        preprocessed = self.preprocess_image(image)

        # 1. Try native Windows.Media.Ocr
        if sys.platform == "win32" and self._win_ocr_script_path and self._win_ocr_script_path.exists():
            win_res = self._extract_via_windows_media_ocr(preprocessed, timeout_sec=timeout_sec)
            if win_res.success and win_res.has_meaningful_content():
                win_res.duration_ms = (time.time() - t0) * 1000
                logger.info(f"[OCR] Extracted {len(win_res.text)} chars across {len(win_res.lines)} lines via Windows.Media.Ocr in {win_res.duration_ms:.1f}ms")
                return win_res
            elif win_res.success and not win_res.has_meaningful_content():
                # Clean pass but image genuinely had no text
                win_res.duration_ms = (time.time() - t0) * 1000
                return win_res

        # 2. Try pytesseract fallback if installed
        tess_res = self._extract_via_pytesseract(preprocessed)
        if tess_res.success and tess_res.has_meaningful_content():
            tess_res.duration_ms = (time.time() - t0) * 1000
            logger.info(f"[OCR] Extracted {len(tess_res.text)} chars via pytesseract in {tess_res.duration_ms:.1f}ms")
            return tess_res

        duration_ms = (time.time() - t0) * 1000
        return OCRResult(
            text="",
            lines=[],
            confidence=0.0,
            engine_used="none",
            success=False,
            duration_ms=duration_ms,
            error="No readable text detected via OCR or engine unavailable"
        )

    def _extract_via_windows_media_ocr(self, image: Image.Image, timeout_sec: float = 8.0) -> OCRResult:
        """Executes Windows.Media.Ocr on a temporary PNG via PowerShell with Base64 decoded response."""
        temp_file = None
        try:
            import base64
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                temp_file = tf.name
                image.save(temp_file, format="PNG")

            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", str(self._win_ocr_script_path),
                temp_file
            ]

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            stdout = proc.stdout.strip()

            if proc.returncode != 0 or not stdout:
                err_msg = proc.stderr.strip() or f"PowerShell exited with code {proc.returncode}"
                logger.debug(f"[OCR] Windows.Media.Ocr invocation failed: {err_msg}")
                return OCRResult(error=err_msg, engine_used="windows_media_ocr", success=False)

            # Parse JSON output
            data = json.loads(stdout, strict=False)
            err_b64 = data.get("error_b64")
            if err_b64:
                err_decoded = base64.b64decode(err_b64).decode("utf-8", errors="replace")
                return OCRResult(error=err_decoded, engine_used="windows_media_ocr", success=False)

            text_b64 = data.get("text_b64", "")
            lines_b64 = data.get("lines_b64", [])

            text = base64.b64decode(text_b64).decode("utf-8", errors="replace").strip() if text_b64 else ""
            lines = [
                base64.b64decode(l).decode("utf-8", errors="replace").strip()
                for l in lines_b64
                if l
            ]
            lines = [l for l in lines if l]

            # Calculate confidence heuristic based on readable character ratio
            alpha_count = sum(1 for c in text if c.isalnum())
            total_count = max(len(text), 1)
            confidence = min(1.0, max(0.5, alpha_count / float(total_count))) if text else 0.0

            return OCRResult(
                text=text,
                lines=lines,
                confidence=confidence,
                engine_used="windows_media_ocr",
                success=True
            )

        except subprocess.TimeoutExpired:
            logger.warning("[OCR] Windows.Media.Ocr timed out.")
            return OCRResult(error="Windows OCR operation timed out", engine_used="windows_media_ocr", success=False)
        except Exception as e:
            logger.debug(f"[OCR] Windows.Media.Ocr error: {e}")
            return OCRResult(error=str(e), engine_used="windows_media_ocr", success=False)
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def _extract_via_pytesseract(self, image: Image.Image) -> OCRResult:
        """Fallback OCR using pytesseract if available."""
        try:
            import pytesseract
            text = pytesseract.image_to_string(image).strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            confidence = 0.85 if text else 0.0
            return OCRResult(
                text=text,
                lines=lines,
                confidence=confidence,
                engine_used="pytesseract",
                success=bool(text)
            )
        except ImportError:
            return OCRResult(error="pytesseract not installed", engine_used="pytesseract", success=False)
        except Exception as e:
            logger.debug(f"[OCR] pytesseract extraction error: {e}")
            return OCRResult(error=str(e), engine_used="pytesseract", success=False)


# Global singleton instance
ocr_engine = OCREngine()
