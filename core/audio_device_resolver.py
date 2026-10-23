"""
Intelligent Audio Device Resolver for Jarvis.
Automatically detects and pairs Bluetooth headsets/earbuds (e.g. Airdopes, AirPods, Galaxy Buds, etc.)
with the active audio input stream, preventing device routing mismatches where output plays to earbuds
while input is mistakenly captured from the laptop's internal microphone.
"""

import re
import logging
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger("Jarvis.AudioDeviceResolver")

# Generic tokens to exclude when extracting hardware device model names
EXCLUDED_TOKENS = {
    "headphones", "headset", "earbuds", "speakers", "speaker", "audio",
    "realtek", "device", "input", "output", "hands-free", "handsfree",
    "directsound", "wasapi", "microsoft", "mapper", "stereo", "capture"
}


def get_all_audio_devices() -> List[Dict[str, Any]]:
    """Returns a list of all audio devices available to sounddevice."""
    try:
        from core.lazy_loader import lazy_import
        sd = lazy_import("sounddevice")
        devices = sd.query_devices()
        return list(devices)
    except Exception as e:
        logger.error(f"Failed to query audio devices: {e}")
        return []


def resolve_audio_input_device(preferred: Optional[Any] = None) -> Tuple[Optional[int], str]:
    """
    Intelligently resolves the audio input device index.

    Priority:
    1. Explicit User Preference (exact index or name substring)
    2. Headset Auto-Pairing: If default audio output is a Bluetooth headset/earbuds,
       automatically pairs with the corresponding headset microphone.
    3. System Default Input Device
    4. First available input device fallback

    Returns:
        Tuple of (device_index, device_name)
    """
    from core.lazy_loader import lazy_import
    sd = lazy_import("sounddevice")

    try:
        devices = list(sd.query_devices())
        def_in, def_out = sd.default.device
    except Exception as e:
        logger.warning(f"Could not query default sound devices: {e}")
        return None, "System Default"

    if not devices:
        return None, "System Default"

    # 1. Check explicit preferred configuration (if not "auto" or None)
    if preferred is not None and str(preferred).strip().lower() not in ["auto", "none", ""]:
        # Numeric index
        if isinstance(preferred, int) or (isinstance(preferred, str) and preferred.strip().isdigit()):
            idx = int(preferred)
            if 0 <= idx < len(devices) and devices[idx]["max_input_channels"] > 0:
                name = devices[idx]["name"]
                logger.info(f"[AUDIO_ROUTER] Using explicitly configured audio input device [{idx}]: {name}")
                return idx, name

        # Name substring match
        pref_str = str(preferred).strip().lower()
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and pref_str in d["name"].lower():
                try:
                    sd.check_input_settings(device=i, samplerate=16000, channels=1)
                    logger.info(f"[AUDIO_ROUTER] Matched explicitly preferred input name '{preferred}' -> [{i}]: {d['name']}")
                    return i, d["name"]
                except Exception:
                    continue

    # 2. Automatic Headset Pairing
    # If the user has Bluetooth earbuds/headset as the default output (e.g. Airdopes, AirPods, Galaxy Buds),
    # find the matching headset microphone.
    if def_out is not None and 0 <= def_out < len(devices):
        out_name = devices[def_out]["name"]
        
        # Tokenize output device name to isolate unique brand/model identifiers
        raw_tokens = re.split(r"[\s\(\)\-_,]+", out_name)
        hardware_tokens = [
            t for t in raw_tokens 
            if len(t) >= 3 and t.lower() not in EXCLUDED_TOKENS
        ]

        if hardware_tokens:
            for token in hardware_tokens:
                token_lower = token.lower()
                for i, d in enumerate(devices):
                    if d["max_input_channels"] > 0 and token_lower in d["name"].lower():
                        # Verify 16kHz mono is supported on this device
                        try:
                            sd.check_input_settings(device=i, samplerate=16000, channels=1)
                            logger.info(
                                f"[AUDIO_ROUTER] Headset auto-pairing active! "
                                f"Output: '{out_name}' -> Matched Input: [{i}] '{d['name']}'"
                            )
                            return i, d["name"]
                        except Exception as check_ex:
                            logger.debug(f"Device [{i}] '{d['name']}' rejected for 16kHz: {check_ex}")
                            continue

    # 3. Fallback to System Default Input Device
    if def_in is not None and 0 <= def_in < len(devices):
        def_name = devices[def_in]["name"]
        try:
            sd.check_input_settings(device=def_in, samplerate=16000, channels=1)
            logger.info(f"[AUDIO_ROUTER] Using system default input device [{def_in}]: {def_name}")
            return def_in, def_name
        except Exception:
            logger.warning(f"Default input device [{def_in}] failed 16kHz check. Searching fallbacks...")

    # 4. Search any valid input device supporting 16kHz
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            try:
                sd.check_input_settings(device=i, samplerate=16000, channels=1)
                logger.info(f"[AUDIO_ROUTER] Fallback input device selected [{i}]: {d['name']}")
                return i, d["name"]
            except Exception:
                continue

    return None, "System Default"
