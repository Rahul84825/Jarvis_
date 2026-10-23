# SANTRA VIRTUAL TESTING ROOM — COMPLETE ARCHITECTURAL SPECIFICATION & CAPABILITY EVALUATION LAB

## Executive Overview

The **SANTRA Virtual Testing Room** is an isolated, deterministic simulation and stress-testing lab engineered directly into the native Python + PyQt6 Santra assistant architecture.

Its mission is to evaluate Santra's intelligence, command accuracy, tool reliability, safety boundaries, and resource limits without manual user trial-and-error and without risk to the user's real desktop files, applications, or external API quotas.

---

## 1. System Inventory & Existing Architecture Audit

| Subsystem | Core Module | Entry Point / Method | Verification Strategy | Current State |
| :--- | :--- | :--- | :--- | :--- |
| **Command Processing** | `core/jarvis_runtime.py` | `JarvisRuntime.process_command(text)` | End-to-end pipeline execution | Fully integrated, supports single & multi-step |
| **Intent Classification** | `core/intent_engine.py` | `IntentEngine.parse(raw_text)` | Deterministic intent parsing | 70+ intents, dedicated regex & semantic routing |
| **Command Normalization**| `core/command_normalizer.py` | `CommandNormalizer.normalize(text)` | Token cleanup, phonetic aliases | Santra wake words, phonetic variations |
| **Tool Registry & Risk** | `core/tool_registry.py` | `ToolRegistry.get_tool(name)` | Tool schema & risk levels | 71 registered capabilities across 18 categories |
| **Safety & Permissions** | `core/tool_safety_gate.py` | `ToolSafetyGate.evaluate(tool, intent)` | Risk gate, confirmation tokens | Gated HIGH-risk operations, confirmation tokens |
| **Command Execution** | `modules/system/executor.py` | `CommandExecutor.execute(node)` | OS, browser, app execution | OS control layer, returns `CommandOutcome` |
| **Browser Automation** | `core/os/browser_intent.py` | `BrowserIntentParser.parse(text)` | CDP and site adapters | URL navigation, site search, tab control |
| **AI Multi-Provider** | `core/ai/provider_manager.py`| `ProviderManager.generate_response()` | Multi-model failover | NVIDIA Nemotron, Gemini, OpenAI, Cerebras |
| **Nemotron Caching** | `core/ai/caching/cache_manager.py` | `NemotronCacheManager.lookup()` | 4-layer cache & single-flight | Exact, Semantic, Task Result, Knowledge |
| **Screen Perception** | `core/vision/screen_explainer.py` | `ScreenExplainer.explain()` | UIA text + vision AI | UIA text extraction, OCR, multimodal fallback |
| **File & Memory** | `core/os/filesystem_manager.py` | `FilesystemManager.save_file()` | Path validation, overwrite guards | Sandboxed workspace indexing & registry |
| **Sleep & Wake Core** | `core/wakeword.py` | `SantraWakeWordDetector.detect()` | Acoustic + energy VAD gating | Native Santra model, trailing command support |

---

## 2. Virtual Testing Room Architecture

The virtual lab architecture consists of:
- **`VirtualLabController`**: Central coordinator and external API facade.
- **`CommandTestRunner`**: Executes scenarios against the real production `IntentEngine`, `CommandNormalizer`, and `ToolRegistry`.
- **`EnvironmentSimulator`**: High-fidelity in-memory computer model representing running apps, open browser tabs, a sandboxed virtual filesystem (temporary directory), and synthetic system telemetry.
- **`MockToolAdapters`**: Interception layer ensuring simulation runs never invoke real desktop OS commands, launch physical processes, modify user documents, or consume paid API tokens.
- **`StateAssertionEngine`**: Deep state validation checking tool selection, argument accuracy, environmental state diffs, safety gate triggers, and failure root cause classification.
- **`ScenarioLibrary`**: Comprehensive, data-driven test scenarios covering all 10 categories.
- **`StressTestManager`**: Bounded, cancellable concurrency and load testing.
- **`TestResultStore`**: SQLite-backed history tracking regression trends.
- **`ReportGenerator`**: Detailed Markdown and JSON diagnostic reports with reproduction commands.
- **`VirtualLabPanel`**: PyQt6 GUI dashboard providing interactive test execution, real-time logs, category filters, and state inspectors.

---

## 3. Two Mandatory Execution Modes

1. **`ExecutionMode.SIMULATION` (Default)**:
   - All external side-effects are intercepted by mock adapters.
   - Applications are simulated in-memory state models.
   - Filesystem operations are strictly bound to a designated temporary directory sandbox.
   - AI calls use mock transports with deterministic responses and simulated latencies.
   - Zero physical OS side-effects; zero risk of data loss.
2. **`ExecutionMode.CONTROLLED_INTEGRATION` (Explicitly Enabled Only)**:
   - Runs against selected real subsystems with clear sandboxing.
   - Reversible test targets only.
   - Never touches user desktop files, external production databases, or paid API quotas.
