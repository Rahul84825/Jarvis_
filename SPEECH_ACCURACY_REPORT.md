# Speech Recognition Accuracy Report

## Summary

| Metric | Original Configuration | New Configuration (Hotfix) |
| :--- | :--- | :--- |
| **Whisper Model Used** | `base` | `small` |
| **Forced Language** | `en` | `en` |
| **Pre-roll Buffer** | None (0.0s) | Enabled (1.0s) |
| **Benchmark Accuracy** | 53.2% (50/94) | 71.3% (67/94) |
| **Average Confidence** | 52.7% | 56.6% |

## Goal Evaluation

* **Goal**: 95%+ recognition accuracy for standard English commands spoken with an Indian accent.
* **Target Reached**: **NO** (Accuracy: **71.3%**)

---

## Command Accuracy Breakdown

| Command | Original (`base`) Accuracy | New (`small`) Accuracy |
| :--- | :--- | :--- |
| Open Chrome | 100.0% | 100.0% |
| Open VS Code | 16.7% | 0.0% |
| Open Downloads | 95.0% | 100.0% |
| Take Screenshot | 0.0% | 89.5% |
| Lock Computer | 50.0% | 61.1% |

---

## Failure Cases Details

### Original Configuration (`base`) Failures

| Filename | Expected | Transcribed | Confidence |
| :--- | :--- | :--- | :--- |
| lock_computer_NeerjaNeural_m10pct.wav | `Lock Computer` | `'log computer'` | 59.4% |
| lock_computer_NeerjaNeural_m15pct.wav | `Lock Computer` | `'log computer'` | 59.2% |
| lock_computer_NeerjaNeural_m20pct.wav | `Lock Computer` | `'log computer'` | 58.8% |
| lock_computer_NeerjaNeural_m5pct.wav | `Lock Computer` | `'log computer'` | 60.8% |
| lock_computer_NeerjaNeural_p0pct.wav | `Lock Computer` | `'log computer'` | 58.2% |
| lock_computer_NeerjaNeural_p10pct.wav | `Lock Computer` | `'log computer'` | 56.4% |
| lock_computer_NeerjaNeural_p15pct.wav | `Lock Computer` | `'log computer'` | 57.2% |
| lock_computer_NeerjaNeural_p20pct.wav | `Lock Computer` | `'log computer'` | 55.3% |
| lock_computer_NeerjaNeural_p25pct.wav | `Lock Computer` | `'log computer'` | 54.1% |
| open_downloads_NeerjaNeural_m15pct.wav | `Open Downloads` | `'Open down loads.'` | 52.3% |
| open_vs_code_NeerjaNeural_m15pct.wav | `Open VS Code` | `'Open Versus Code'` | 50.2% |
| open_vs_code_NeerjaNeural_m20pct.wav | `Open VS Code` | `'Open Versus Code'` | 47.3% |
| open_vs_code_NeerjaNeural_m5pct.wav | `Open VS Code` | `'Open vs. Good'` | 54.4% |
| open_vs_code_NeerjaNeural_p15pct.wav | `Open VS Code` | `'Open verse is good.'` | 50.3% |
| open_vs_code_NeerjaNeural_p20pct.wav | `Open VS Code` | `'Open verse is good.'` | 48.6% |
| open_vs_code_NeerjaNeural_p5pct.wav | `Open VS Code` | `'Open Versus Code.'` | 50.8% |
| open_vs_code_PrabhatNeural_m10pct.wav | `Open VS Code` | `'Open Versus Code.'` | 44.3% |
| open_vs_code_PrabhatNeural_m15pct.wav | `Open VS Code` | `'Open Versus Code.'` | 47.2% |
| open_vs_code_PrabhatNeural_m20pct.wav | `Open VS Code` | `'Open Versus Code.'` | 47.9% |
| open_vs_code_PrabhatNeural_m5pct.wav | `Open VS Code` | `'Open Versus Code.'` | 44.7% |
| open_vs_code_PrabhatNeural_p0pct.wav | `Open VS Code` | `'Open Versus Code.'` | 48.7% |
| open_vs_code_PrabhatNeural_p10pct.wav | `Open VS Code` | `'Open Versus Code.'` | 47.4% |
| open_vs_code_PrabhatNeural_p15pct.wav | `Open VS Code` | `'Open versus Code.'` | 43.8% |
| open_vs_code_PrabhatNeural_p25pct.wav | `Open VS Code` | `'Open Versus Code.'` | 46.4% |
| open_vs_code_PrabhatNeural_p5pct.wav | `Open VS Code` | `'Open Versus Code.'` | 45.9% |
| take_screenshot_NeerjaNeural_m10pct.wav | `Take Screenshot` | `'take screen shot.'` | 49.4% |
| take_screenshot_NeerjaNeural_m20pct.wav | `Take Screenshot` | `'take screen shot'` | 52.7% |
| take_screenshot_NeerjaNeural_m5pct.wav | `Take Screenshot` | `'take screen shot'` | 55.8% |
| take_screenshot_NeerjaNeural_p0pct.wav | `Take Screenshot` | `'take screen shot'` | 53.1% |
| take_screenshot_NeerjaNeural_p10pct.wav | `Take Screenshot` | `'take screen shot.'` | 43.6% |
| take_screenshot_NeerjaNeural_p15pct.wav | `Take Screenshot` | `'take screen shot.'` | 37.5% |
| take_screenshot_NeerjaNeural_p20pct.wav | `Take Screenshot` | `'Next, screenshot.'` | 43.7% |
| take_screenshot_NeerjaNeural_p25pct.wav | `Take Screenshot` | `'take screen shot.'` | 38.9% |
| take_screenshot_NeerjaNeural_p5pct.wav | `Take Screenshot` | `'take screen shot'` | 50.7% |
| take_screenshot_PrabhatNeural_m10pct.wav | `Take Screenshot` | `'take screen shot'` | 53.5% |
| take_screenshot_PrabhatNeural_m15pct.wav | `Take Screenshot` | `'X-screen shot'` | 51.8% |
| take_screenshot_PrabhatNeural_m20pct.wav | `Take Screenshot` | `'take screen shot.'` | 50.1% |
| take_screenshot_PrabhatNeural_m5pct.wav | `Take Screenshot` | `'take screen shot'` | 49.8% |
| take_screenshot_PrabhatNeural_p0pct.wav | `Take Screenshot` | `'take screen shot'` | 46.3% |
| take_screenshot_PrabhatNeural_p10pct.wav | `Take Screenshot` | `'take screen shot'` | 47.1% |
| take_screenshot_PrabhatNeural_p15pct.wav | `Take Screenshot` | `'take screen shot'` | 42.8% |
| take_screenshot_PrabhatNeural_p20pct.wav | `Take Screenshot` | `'take screen shot'` | 48.1% |
| take_screenshot_PrabhatNeural_p25pct.wav | `Take Screenshot` | `'take screen shot.'` | 40.9% |
| take_screenshot_PrabhatNeural_p5pct.wav | `Take Screenshot` | `'take screen shot'` | 49.3% |

### New Configuration (`small`) Failures

| Filename | Expected | Transcribed | Confidence |
| :--- | :--- | :--- | :--- |
| lock_computer_NeerjaNeural_m10pct.wav | `Lock Computer` | `'Logcomputer'` | 44.9% |
| lock_computer_NeerjaNeural_m15pct.wav | `Lock Computer` | `'Logcomputer'` | 44.2% |
| lock_computer_NeerjaNeural_m20pct.wav | `Lock Computer` | `'Logcomputer'` | 41.6% |
| lock_computer_NeerjaNeural_m5pct.wav | `Lock Computer` | `'Log computer'` | 45.6% |
| lock_computer_NeerjaNeural_p0pct.wav | `Lock Computer` | `'Log computer'` | 43.5% |
| lock_computer_NeerjaNeural_p15pct.wav | `Lock Computer` | `'Logcomputer.'` | 41.9% |
| lock_computer_NeerjaNeural_p20pct.wav | `Lock Computer` | `'Logcomputer.'` | 40.0% |
| open_vs_code_NeerjaNeural_m15pct.wav | `Open VS Code` | `'Open Versus Code'` | 56.9% |
| open_vs_code_NeerjaNeural_m20pct.wav | `Open VS Code` | `'Open Versus Code'` | 54.6% |
| open_vs_code_NeerjaNeural_m5pct.wav | `Open VS Code` | `'Open versus code.'` | 56.6% |
| open_vs_code_NeerjaNeural_p0pct.wav | `Open VS Code` | `'Open Versus Code'` | 55.8% |
| open_vs_code_NeerjaNeural_p10pct.wav | `Open VS Code` | `'Open versus code.'` | 55.9% |
| open_vs_code_NeerjaNeural_p15pct.wav | `Open VS Code` | `'Open Versus Code'` | 54.9% |
| open_vs_code_NeerjaNeural_p20pct.wav | `Open VS Code` | `'Open versus code.'` | 53.5% |
| open_vs_code_NeerjaNeural_p5pct.wav | `Open VS Code` | `'Open Versus Code.'` | 56.5% |
| open_vs_code_PrabhatNeural_m10pct.wav | `Open VS Code` | `'Open versus code.'` | 56.1% |
| open_vs_code_PrabhatNeural_m15pct.wav | `Open VS Code` | `'open versus code'` | 55.1% |
| open_vs_code_PrabhatNeural_m20pct.wav | `Open VS Code` | `'Open versus code.'` | 54.2% |
| open_vs_code_PrabhatNeural_m5pct.wav | `Open VS Code` | `'Open versus code.'` | 54.8% |
| open_vs_code_PrabhatNeural_p0pct.wav | `Open VS Code` | `'Open versus code.'` | 52.7% |
| open_vs_code_PrabhatNeural_p10pct.wav | `Open VS Code` | `'Open versus code.'` | 56.3% |
| open_vs_code_PrabhatNeural_p15pct.wav | `Open VS Code` | `'Open versus code.'` | 54.2% |
| open_vs_code_PrabhatNeural_p20pct.wav | `Open VS Code` | `'Open versus code.'` | 54.5% |
| open_vs_code_PrabhatNeural_p25pct.wav | `Open VS Code` | `'Open versus code.'` | 54.2% |
| open_vs_code_PrabhatNeural_p5pct.wav | `Open VS Code` | `'Open versus code.'` | 57.1% |
| take_screenshot_PrabhatNeural_m15pct.wav | `Take Screenshot` | `'Take screen shot.'` | 69.2% |
| take_screenshot_PrabhatNeural_p25pct.wav | `Take Screenshot` | `'Take screen shot.'` | 66.9% |

