import os
import sys
import asyncio
import time
import math
import re
import logging
from pathlib import Path
import av
import numpy as np
import soundfile as sf
import edge_tts
from core.transcriber import SpeechTranscriber

# Set up simple logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Benchmark")

COMMANDS = [
    "Open Chrome",
    "Open VS Code",
    "Open Downloads",
    "Take Screenshot",
    "Lock Computer"
]

VOICES = [
    "en-IN-NeerjaNeural", # Female Indian English
    "en-IN-PrabhatNeural" # Male Indian English
]

RATES = ["-20%", "-15%", "-10%", "-5%", "+0%", "+5%", "+10%", "+15%", "+20%", "+25%"]

AUDIO_DIR = Path("C:/Users/activ/Desktop/Jarvis/logs/benchmark_audio")

def clean(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text) # remove punctuation
    return " ".join(text.split())

def convert_mp3_to_wav(mp3_path, wav_path, target_sr=16000):
    container = av.open(str(mp3_path))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format='s16', layout='mono', rate=target_sr)
    
    audio_data = []
    for frame in container.decode(stream):
        resampled_frames = resampler.resample(frame)
        for r_frame in resampled_frames:
            arr = r_frame.to_ndarray()
            audio_data.append(arr)
            
    if audio_data:
        full_audio = np.concatenate(audio_data, axis=1) # (1, samples)
        full_audio = full_audio.flatten()
        sf.write(str(wav_path), full_audio, target_sr, subtype='PCM_16')
    container.close()

async def generate_benchmark_audio():
    AUDIO_DIR.mkdir(exist_ok=True, parents=True)
    logger.info("Generating benchmark audio files using edge-tts...")
    
    tasks = []
    for cmd in COMMANDS:
        for voice in VOICES:
            for rate in RATES:
                # Replace spaces with underscores for filenames
                safe_cmd = cmd.lower().replace(" ", "_")
                filename_base = f"{safe_cmd}_{voice.split('-')[2]}_{rate.replace('%', 'pct').replace('+', 'p').replace('-', 'm')}"
                mp3_path = AUDIO_DIR / f"{filename_base}.mp3"
                wav_path = AUDIO_DIR / f"{filename_base}.wav"
                
                if wav_path.exists():
                    # Skip if already generated
                    continue
                    
                # We will synthesize the text
                async def synth_and_convert(c_text, v_name, r_val, m_path, w_path):
                    try:
                        communicate = edge_tts.Communicate(c_text, v_name, rate=r_val)
                        await communicate.save(str(m_path))
                        # Convert to WAV
                        convert_mp3_to_wav(m_path, w_path)
                        # Remove MP3
                        if m_path.exists():
                            m_path.unlink()
                    except Exception as e:
                        logger.error(f"Failed to generate {w_path.name}: {e}")
                        
                tasks.append(synth_and_convert(cmd, voice, rate, mp3_path, wav_path))
                
    if tasks:
        await asyncio.gather(*tasks)
    logger.info(f"Audio generation complete. Total WAV files in {AUDIO_DIR}: {len(list(AUDIO_DIR.glob('*.wav')))}")

def run_transcriptions(model_size):
    logger.info(f"Loading transcriber with model: {model_size}...")
    transcriber = SpeechTranscriber(model_size=model_size, device="cpu")
    
    results = []
    
    wav_files = sorted(list(AUDIO_DIR.glob("*.wav")))
    total = len(wav_files)
    
    for idx, wav_path in enumerate(wav_files):
        # Determine expected command from filename
        filename = wav_path.stem
        # Match expected command
        expected_cmd = None
        for cmd in COMMANDS:
            if filename.startswith(cmd.lower().replace(" ", "_")):
                expected_cmd = cmd
                break
                
        if not expected_cmd:
            continue
            
        logger.info(f"[{model_size}] Processing file {idx+1}/{total}: {wav_path.name}")
        t0 = time.time()
        try:
            transcription = transcriber.transcribe(str(wav_path))
            meta = transcriber.last_metadata
            confidence = meta["confidence"]
            duration = meta["duration"]
        except Exception as e:
            logger.error(f"Error transcribing {wav_path.name}: {e}")
            transcription = ""
            confidence = 0.0
            duration = 0.0
            
        # Check match
        matched = clean(transcription) == clean(expected_cmd)
        results.append({
            "filename": wav_path.name,
            "expected": expected_cmd,
            "transcription": transcription,
            "confidence": confidence,
            "duration": duration,
            "matched": matched,
            "latency": time.time() - t0
        })
        
    return results

def generate_report(base_results, small_results):
    report_path = Path("C:/Users/activ/Desktop/Jarvis/SPEECH_ACCURACY_REPORT.md")
    
    # Calculate stats
    base_correct = sum(1 for r in base_results if r["matched"])
    base_acc = (base_correct / len(base_results)) * 100 if base_results else 0.0
    
    small_correct = sum(1 for r in small_results if r["matched"])
    small_acc = (small_correct / len(small_results)) * 100 if small_results else 0.0
    
    base_conf = sum(r["confidence"] for r in base_results) / len(base_results) if base_results else 0.0
    small_conf = sum(r["confidence"] for r in small_results) / len(small_results) if small_results else 0.0
    
    # Failure cases
    base_failures = [r for r in base_results if not r["matched"]]
    small_failures = [r for r in small_results if not r["matched"]]
    
    md_content = f"""# Speech Recognition Accuracy Report

## Summary

| Metric | Original Configuration | New Configuration (Hotfix) |
| :--- | :--- | :--- |
| **Whisper Model Used** | `base` | `small` |
| **Forced Language** | `en` | `en` |
| **Pre-roll Buffer** | None (0.0s) | Enabled (1.0s) |
| **Benchmark Accuracy** | {base_acc:.1f}% ({base_correct}/{len(base_results)}) | {small_acc:.1f}% ({small_correct}/{len(small_results)}) |
| **Average Confidence** | {base_conf*100:.1f}% | {small_conf*100:.1f}% |

## Goal Evaluation

* **Goal**: 95%+ recognition accuracy for standard English commands spoken with an Indian accent.
* **Target Reached**: {"**YES**" if small_acc >= 95.0 else "**NO**"} (Accuracy: **{small_acc:.1f}%**)

---

## Command Accuracy Breakdown

| Command | Original (`base`) Accuracy | New (`small`) Accuracy |
| :--- | :--- | :--- |
"""
    for cmd in COMMANDS:
        cmd_base = [r for r in base_results if r["expected"] == cmd]
        cmd_small = [r for r in small_results if r["expected"] == cmd]
        
        base_cmd_acc = (sum(1 for r in cmd_base if r["matched"]) / len(cmd_base)) * 100 if cmd_base else 0.0
        small_cmd_acc = (sum(1 for r in cmd_small if r["matched"]) / len(cmd_small)) * 100 if cmd_small else 0.0
        
        md_content += f"| {cmd} | {base_cmd_acc:.1f}% | {small_cmd_acc:.1f}% |\n"
        
    md_content += """
---

## Failure Cases Details

"""
    if base_failures:
        md_content += "### Original Configuration (`base`) Failures\n\n"
        md_content += "| Filename | Expected | Transcribed | Confidence |\n"
        md_content += "| :--- | :--- | :--- | :--- |\n"
        for f in base_failures:
            # Escape single quotes and display text nicely
            escaped_trans = f['transcription'].replace("'", "\\'")
            md_content += f"| {f['filename']} | `{f['expected']}` | `'{escaped_trans}'` | {f['confidence']*100:.1f}% |\n"
        md_content += "\n"
    else:
        md_content += "### Original Configuration (`base`) Failures\n\nNone.\n\n"
        
    if small_failures:
        md_content += "### New Configuration (`small`) Failures\n\n"
        md_content += "| Filename | Expected | Transcribed | Confidence |\n"
        md_content += "| :--- | :--- | :--- | :--- |\n"
        for f in small_failures:
            escaped_trans = f['transcription'].replace("'", "\\'")
            md_content += f"| {f['filename']} | `{f['expected']}` | `'{escaped_trans}'` | {f['confidence']*100:.1f}% |\n"
        md_content += "\n"
    else:
        md_content += "### New Configuration (`small`) Failures\n\nNone.\n\n"
        
    report_path.write_text(md_content, encoding="utf-8")
    logger.info(f"Benchmark report generated at: {report_path}")

async def main():
    await generate_benchmark_audio()
    
    # Run original model benchmark
    base_results = run_transcriptions("base")
    
    # Run new model benchmark
    small_results = run_transcriptions("small")
    
    # Generate the accuracy report
    generate_report(base_results, small_results)

if __name__ == "__main__":
    asyncio.run(main())
