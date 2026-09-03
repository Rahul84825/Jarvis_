# Speech Recognition Accuracy Report

## Summary

| Metric | Original Configuration | New Configuration (Hotfix) |
| :--- | :--- | :--- |
| **Whisper Model Used** | `base` | `small` |
| **Forced Language** | `en` | `en` |
| **Pre-roll Buffer** | None (0.0s) | Enabled (1.0s) |
| **Benchmark Accuracy** | 100.0% (100/100) | 100.0% (100/100) |
| **Average Confidence** | 67.9% | 60.3% |

## Goal Evaluation

* **Goal**: 95%+ recognition accuracy for standard English commands spoken with an Indian accent.
* **Target Reached**: **YES** (Accuracy: **100.0%**)

---

## Command Accuracy Breakdown

| Command | Original (`base`) Accuracy | New (`small`) Accuracy |
| :--- | :--- | :--- |
| Open Chrome | 100.0% | 100.0% |
| Open VS Code | 100.0% | 100.0% |
| Open Downloads | 100.0% | 100.0% |
| Take Screenshot | 100.0% | 100.0% |
| Lock Computer | 100.0% | 100.0% |

---

## Failure Cases Details

### Original Configuration (`base`) Failures

None.

### New Configuration (`small`) Failures

None.

