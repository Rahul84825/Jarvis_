import os
import sys
import time
import sounddevice as sd
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from core.jarvis_runtime import JarvisRuntime
from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider

def generate_command_wavs():
    sapi = WindowsSAPIProvider()
    commands = [
        ("hello_jarvis", "Hello Jarvis"),
        ("what_can_you_do", "What can you do?"),
        ("open_chrome", "Open Chrome"),
        ("open_spotify", "Open Spotify"),
        ("open_youtube", "Open YouTube"),
        ("take_a_photo", "Take a photo")
    ]
    
    out_dir = Path("logs/test_hardware_commands")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    wav_files = {}
    for key, text in commands:
        wav_path = out_dir / f"{key}.wav"
        if not wav_path.exists() or wav_path.stat().st_size == 0:
            print(f"Synthesizing test input speech: '{text}' -> {wav_path.name}")
            generated = sapi.synthesize_to_file(text)
            if generated and os.path.exists(generated):
                import shutil
                shutil.copyfile(generated, wav_path)
                try:
                    os.remove(generated)
                except Exception:
                    pass
        wav_files[text] = str(wav_path)
    return wav_files

def main():
    print("="*80)
    print("JARVIS REAL HARDWARE AUDIO & TRANSCRIPTION PIPELINE TEST")
    print("="*80)
    
    # 1. Output device check
    devs = sd.query_devices()
    def_out_idx = sd.default.device[1]
    def_out_info = devs[def_out_idx]
    print(f"Default Output Device: [{def_out_idx}] {def_out_info['name']}")
    print(f"Host API: {sd.query_hostapis(def_out_info['hostapi'])['name']}")
    print(f"Default Sample Rate: {def_out_info['default_samplerate']} Hz")
    print(f"Max Output Channels: {def_out_info['max_output_channels']}")
    print("="*80)

    # 2. Generate command speech WAVs
    wav_files = generate_command_wavs()

    # 3. Initialize JarvisRuntime
    print("\n[INIT] Initializing Jarvis Runtime Core...")
    runtime = JarvisRuntime()
    runtime.tts_manager.start()
    
    # Ensure transcriber model is warm
    print("[INIT] Pre-warming Whisper model...")
    runtime.transcriber._load_model()
    print("[INIT] Whisper model ready.")

    results = []

    print("\nExecuting Hardware Test Commands on Real Audio Pipeline...\n")
    for cmd_text, wav_path in wav_files.items():
        print(f"============================================================")
        print(f"TESTING COMMAND: '{cmd_text}'")
        print(f"============================================================")
        
        # Copy audio file because _on_speech_end removes temporary files
        test_wav = str(Path(wav_path).with_suffix(".tmp.wav"))
        import shutil
        shutil.copyfile(wav_path, test_wav)

        timings = {}
        captured_data = {}
        
        # Intercept functions
        orig_transcribe = runtime.transcriber.transcribe
        orig_tts_speak = runtime.tts_manager.speak
        orig_play = runtime.tts_manager._play_audio_file
        
        def wrapped_transcribe(audio_file):
            res = orig_transcribe(audio_file)
            timings['transcription_available'] = time.time()
            captured_data['transcription_text'] = res
            return res
            
        def wrapped_tts_speak(response_text, *args, **kwargs):
            if 'response_generated' not in timings:
                timings['response_generated'] = time.time()
                captured_data['response_text'] = response_text
            return orig_tts_speak(response_text, *args, **kwargs)
            
        def wrapped_play(audio_path):
            timings['tts_synthesis_complete'] = time.time()
            timings['first_audible_sound'] = time.time()
            return orig_play(audio_path)

        runtime.transcriber.transcribe = wrapped_transcribe
        runtime.tts_manager.speak = wrapped_tts_speak
        runtime.tts_manager._play_audio_file = wrapped_play

        t_speech_end = time.time()
        timings['speech_end'] = t_speech_end

        try:
            runtime._on_speech_end(test_wav)
            
            # Wait for physical audio playback to complete through soundcard
            runtime.tts_manager.wait_until_finished(timeout=10.0)
            time.sleep(0.5)

            # Restore original functions
            runtime.transcriber.transcribe = orig_transcribe
            runtime.tts_manager.speak = orig_tts_speak
            runtime.tts_manager._play_audio_file = orig_play

            # Validate success
            sound_produced = 'first_audible_sound' in timings
            status = "PASS" if sound_produced else "FAIL"
            
            speech_to_transcript = (timings.get('transcription_available', 0) - timings['speech_end']) * 1000
            speech_to_first_sound = (timings.get('first_audible_sound', 0) - timings['speech_end']) * 1000

            results.append({
                "command": cmd_text,
                "status": status,
                "speech_end": timings['speech_end'],
                "transcription_available": timings.get('transcription_available', 0),
                "response_generated": timings.get('response_generated', 0),
                "tts_synthesis_complete": timings.get('tts_synthesis_complete', 0),
                "first_audible_sound": timings.get('first_audible_sound', 0),
                "speech_to_transcript_ms": speech_to_transcript,
                "speech_to_first_sound_ms": speech_to_first_sound,
                "transcription": captured_data.get('transcription_text', ''),
                "response": captured_data.get('response_text', '')
            })

            print(f"\n--- Result for '{cmd_text}': {status} ---")
            print(f"  Speech End:              {timings['speech_end']:.4f}")
            print(f"  Transcription Available: {timings.get('transcription_available', 0):.4f} (latency: {speech_to_transcript:.1f}ms, recognized: '{captured_data.get('transcription_text', '')}')")
            print(f"  Response Generated:      {timings.get('response_generated', 0):.4f} (response: '{captured_data.get('response_text', '')}')")
            print(f"  TTS Synthesis Complete:  {timings.get('tts_synthesis_complete', 0):.4f}")
            print(f"  FIRST AUDIBLE SOUND:     {timings.get('first_audible_sound', 0):.4f} (total latency: {speech_to_first_sound:.1f}ms)\n")

        except Exception as e:
            print(f"Error executing command test '{cmd_text}': {e}")
            results.append({
                "command": cmd_text,
                "status": "FAIL",
                "error": str(e)
            })

    runtime.stop()

    print("\n" + "="*80)
    print("SECTION 19 REAL HARDWARE TEST RESULTS")
    print("="*80)
    for r in results:
        cmd = r['command']
        st = r['status']
        if st == "PASS":
            print(f'"{cmd}" -> {st} (Speech->STT: {r["speech_to_transcript_ms"]:.0f}ms | Total to Sound: {r["speech_to_first_sound_ms"]:.0f}ms | Heard: "{r["response"]}")')
        else:
            print(f'"{cmd}" -> {st}')
    print("="*80)

if __name__ == "__main__":
    main()
