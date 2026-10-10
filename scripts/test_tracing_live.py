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

def test_live_commands():
    print("=" * 80)
    print("JARVIS LIVE RUNTIME TRACING AUDIT EXECUTION")
    print("=" * 80)
    
    runtime = JarvisRuntime()
    runtime.start()
    time.sleep(1.0)

    # 1. Test Command A: "what time is it" (L1 Local System Info)
    print("\n[TEST 1] Executing Command: 'what time is it'")
    trace1 = tracer.start_trace("trace-live-time-001")
    runtime.process_command("what time is it")
    
    # Wait for TTS audio playback to complete physically
    runtime.tts_manager.wait_until_finished(timeout=6.0)
    time.sleep(0.5)

    trace1_data = trace1.to_dict()
    print("\n--- Trace 1 Summary (Local L1 Time Query) ---")
    print(f"Correlation ID:        {trace1_data['correlation_id']}")
    print(f"Status:                {trace1_data['status']}")
    print(f"Intelligence Layer:    {trace1_data['intelligence_layer']}")
    print(f"Recognized:            '{trace1_data['recognized_text']}'")
    print(f"Normalized:            '{trace1_data['normalized_text']}'")
    print(f"Intent / Action:       {trace1_data['intent']} / {trace1_data['action']}")
    print("Milestones (ms):")
    for k, v in trace1_data['milestones'].items():
        print(f"  {k:35}: {v} ms")
    print("Playback Verification:")
    for k, v in trace1_data['playback_info'].items():
        print(f"  {k:25}: {v}")
    print("Tool Spans:")
    for tool in trace1_data['tool_executions']:
        print(f"  [{tool['category']}] {tool['name']}: {tool['duration_ms']}ms (success={tool['success']})")

    # 2. Test Command B: Audio Speech File Simulation (End-to-End Voice Capture -> STT -> Exec -> TTS)
    test_wav = "logs/benchmark_audio/open_chrome_PrabhatNeural_p0pct.wav"
    if os.path.exists(test_wav):
        print("\n" + "=" * 80)
        print(f"[TEST 2] Executing Voice Command Pipeline from Audio WAV: {test_wav}")
        # Copy to temp file since _on_speech_end deletes input file
        import tempfile, shutil
        fd, tmp_copy = tempfile.mkstemp(suffix=".wav", prefix="test_trace_wav_")
        os.close(fd)
        shutil.copyfile(test_wav, tmp_copy)

        # Trigger speech end directly
        runtime._on_speech_end(tmp_copy)
        
        # Wait for TTS audio playback
        runtime.tts_manager.wait_until_finished(timeout=8.0)
        time.sleep(0.5)
        
        current_trace = tracer.get_current_trace()
        if current_trace:
            trace2_data = current_trace.to_dict()
            print("\n--- Trace 2 Summary (Speech-to-Sound Full Pipeline) ---")
            print(f"Correlation ID:        {trace2_data['correlation_id']}")
            print(f"Status:                {trace2_data['status']}")
            print(f"Intelligence Layer:    {trace2_data['intelligence_layer']}")
            print(f"Recognized:            '{trace2_data['recognized_text']}'")
            print(f"Normalized:            '{trace2_data['normalized_text']}'")
            print(f"Intent / Action:       {trace2_data['intent']} / {trace2_data['action']}")
            print("Milestones (ms):")
            for k, v in trace2_data['milestones'].items():
                print(f"  {k:35}: {v} ms")
            print("Playback Verification:")
            for k, v in trace2_data['playback_info'].items():
                print(f"  {k:25}: {v}")
            print("Tool Spans:")
            for tool in trace2_data['tool_executions']:
                print(f"  [{tool['category']}] {tool['name']}: {tool['duration_ms']}ms (success={tool['success']})")

    runtime.stop()
    print("\n" + "=" * 80)
    print("Live tracing audit run completed successfully.")
    print("=" * 80)

if __name__ == "__main__":
    test_live_commands()
