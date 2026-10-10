import os
import sys
import time
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from core.jarvis_runtime import JarvisRuntime
from core.tracing import tracer
from core.transcriber import SpeechTranscriber
from unittest.mock import patch

def run_search_smoke_tests():
    print("=" * 80)
    print("JARVIS REAL RUNTIME SEARCH SMOKE TESTS")
    print("=" * 80)

    runtime = JarvisRuntime()
    # Mock browser open to avoid opening dozens of live browser windows during smoke test
    real_open = runtime.executor.browser_mgr.open_browser

    reports = []

    # -------------------------------------------------------------
    # 1. Text Command 1: "Jarvis search latest AI news"
    # -------------------------------------------------------------
    print("\n[SMOKE 1] 'Jarvis search latest AI news'")
    with patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True) as mock_open:
        trace = tracer.start_trace("smoke-search-001")
        res = runtime._process_single_command("Jarvis search latest AI news", speak=False)
        report1 = {
            "test_id": 1,
            "raw_input": "Jarvis search latest AI news",
            "transcribed_input": "Jarvis search latest AI news (Text Pipeline)",
            "normalized_input": trace.normalized_text,
            "detected_intent": trace.intent,
            "extracted_query": runtime.intent_engine.parse("Jarvis search latest AI news")["query"],
            "selected_provider_tool": f"BrowserManager.search ({runtime.intent_engine.parse('Jarvis search latest AI news')['provider']})",
            "provider_invoked": mock_open.called,
            "results_received": res.get("success", False),
            "final_response": res.get("message", ""),
            "reached_local_fallback": "limited to my local capabilities" in res.get("message", "").lower()
        }
        reports.append(report1)

    # -------------------------------------------------------------
    # 2. Text Command 2: "Jarvis search what is quantum computing"
    # -------------------------------------------------------------
    print("\n[SMOKE 2] 'Jarvis search what is quantum computing'")
    with patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True) as mock_open:
        trace = tracer.start_trace("smoke-search-002")
        res = runtime._process_single_command("Jarvis search what is quantum computing", speak=False)
        report2 = {
            "test_id": 2,
            "raw_input": "Jarvis search what is quantum computing",
            "transcribed_input": "Jarvis search what is quantum computing (Text Pipeline)",
            "normalized_input": trace.normalized_text,
            "detected_intent": trace.intent,
            "extracted_query": runtime.intent_engine.parse("Jarvis search what is quantum computing")["query"],
            "selected_provider_tool": f"BrowserManager.search ({runtime.intent_engine.parse('Jarvis search what is quantum computing')['provider']})",
            "provider_invoked": mock_open.called,
            "results_received": res.get("success", False),
            "final_response": res.get("message", ""),
            "reached_local_fallback": "limited to my local capabilities" in res.get("message", "").lower()
        }
        reports.append(report2)

    # -------------------------------------------------------------
    # 3. Text Command 3: "Jarvis search official React documentation"
    # -------------------------------------------------------------
    print("\n[SMOKE 3] 'Jarvis search official React documentation'")
    with patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True) as mock_open:
        trace = tracer.start_trace("smoke-search-003")
        res = runtime._process_single_command("Jarvis search official React documentation", speak=False)
        report3 = {
            "test_id": 3,
            "raw_input": "Jarvis search official React documentation",
            "transcribed_input": "Jarvis search official React documentation (Text Pipeline)",
            "normalized_input": trace.normalized_text,
            "detected_intent": trace.intent,
            "extracted_query": runtime.intent_engine.parse("Jarvis search official React documentation")["query"],
            "selected_provider_tool": f"BrowserManager.search ({runtime.intent_engine.parse('Jarvis search official React documentation')['provider']})",
            "provider_invoked": mock_open.called,
            "results_received": res.get("success", False),
            "final_response": res.get("message", ""),
            "reached_local_fallback": "limited to my local capabilities" in res.get("message", "").lower()
        }
        reports.append(report3)

    # -------------------------------------------------------------
    # 4. Text Command 4: "Jarvis search" (Empty query clarification)
    # -------------------------------------------------------------
    print("\n[SMOKE 4] 'Jarvis search'")
    with patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True) as mock_open:
        trace = tracer.start_trace("smoke-search-004")
        res = runtime._process_single_command("Jarvis search", speak=False)
        report4 = {
            "test_id": 4,
            "raw_input": "Jarvis search",
            "transcribed_input": "Jarvis search (Text Pipeline)",
            "normalized_input": trace.normalized_text,
            "detected_intent": trace.intent,
            "extracted_query": runtime.intent_engine.parse("Jarvis search")["query"],
            "selected_provider_tool": "Clarification Handler (Empty Query)",
            "provider_invoked": mock_open.called,
            "results_received": res.get("success", False),
            "final_response": res.get("message", ""),
            "reached_local_fallback": "limited to my local capabilities" in res.get("message", "").lower()
        }
        reports.append(report4)

    # -------------------------------------------------------------
    # 5. Controlled Test 5: Missing / Unconfigured Provider
    # -------------------------------------------------------------
    print("\n[SMOKE 5] 'Jarvis search unconfigured provider'")
    node = {
        "intent": "web_search",
        "action": "search",
        "provider": "unconfigured_engine",
        "target": "Python 3.14",
        "query": "Python 3.14",
        "empty_query": False,
        "is_explicit_search": True
    }
    res5 = runtime.executor.execute(node)
    report5 = {
        "test_id": 5,
        "raw_input": "Manual execution with unconfigured provider",
        "transcribed_input": "N/A (Direct Intent Node)",
        "normalized_input": "search Python 3.14",
        "detected_intent": "web_search",
        "extracted_query": "Python 3.14",
        "selected_provider_tool": "BrowserManager.search (unconfigured_engine)",
        "provider_invoked": False,
        "results_received": res5.get("success", False),
        "final_response": res5.get("message", ""),
        "reached_local_fallback": "limited to my local capabilities" in res5.get("message", "").lower()
    }
    reports.append(report5)

    # -------------------------------------------------------------
    # 6. Controlled Test 6: Search Service / Browser Unavailable
    # -------------------------------------------------------------
    print("\n[SMOKE 6] Search when browser is unavailable")
    with patch.object(runtime.executor.browser_mgr, "resolve_target_browser", return_value=(None, "No supported browser found.")):
        node6 = {
            "intent": "web_search",
            "action": "search",
            "provider": "google",
            "target": "Python",
            "query": "Python",
            "empty_query": False,
            "is_explicit_search": True
        }
        res6 = runtime.executor.execute(node6)
        report6 = {
            "test_id": 6,
            "raw_input": "Search with browser unavailable",
            "transcribed_input": "N/A (Controlled Test)",
            "normalized_input": "search Python",
            "detected_intent": "web_search",
            "extracted_query": "Python",
            "selected_provider_tool": "BrowserManager.search (google)",
            "provider_invoked": False,
            "results_received": res6.get("success", False),
            "final_response": res6.get("message", ""),
            "reached_local_fallback": "limited to my local capabilities" in res6.get("message", "").lower()
        }
        reports.append(report6)

    # -------------------------------------------------------------
    # 7. Real Voice Path Smoke Test (Whisper STT -> Routing)
    # -------------------------------------------------------------
    print("\n[SMOKE 7] Voice Speech Audio Pipeline (Whisper -> Search)")
    try:
        from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider

        # Synthesize real speech WAV to simulate user voice "Jarvis search latest AI news"
        sapi = WindowsSAPIProvider()
        temp_wav = sapi.synthesize_to_file("Jarvis search latest AI news")
        print(f"Generated Voice Speech WAV: {temp_wav}")

        # Run through SpeechTranscriber (Faster-Whisper)
        transcriber = SpeechTranscriber(model_size="base", device="cpu", beam_size=1)
        transcribed_text = transcriber.transcribe(temp_wav)
        print(f"Real Whisper Transcribed Text: '{transcribed_text}'")

        with patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True) as mock_voice_open:
            voice_res = runtime._process_single_command(transcribed_text, raw_full_text=transcribed_text, speak=False)
            node_v = runtime.intent_engine.parse(transcribed_text)
            report7 = {
                "test_id": 7,
                "raw_input": "Synthesized voice: 'Jarvis search latest AI news'",
                "transcribed_input": f"Whisper Transcribed: '{transcribed_text}'",
                "normalized_input": runtime.normalizer.normalize(transcribed_text)["normalized"],
                "detected_intent": node_v["intent"],
                "extracted_query": node_v["query"],
                "selected_provider_tool": f"BrowserManager.search ({node_v['provider']})",
                "provider_invoked": mock_voice_open.called,
                "results_received": voice_res.get("success", False),
                "final_response": voice_res.get("message", ""),
                "reached_local_fallback": "limited to my local capabilities" in voice_res.get("message", "").lower()
            }
            reports.append(report7)
    except Exception as e:
        print(f"Voice smoke test note: {e}")

    print("\n" + "=" * 80)
    print("SMOKE TEST RESULTS SUMMARY")
    print("=" * 80)
    print(json.dumps(reports, indent=2))

    # Write results to artifact scratch
    with open("logs/smoke_search_results.json", "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)

if __name__ == "__main__":
    run_search_smoke_tests()
