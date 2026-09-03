# Multi-Command Execution Engine Architecture

## Overview
Jarvis supports natural multi-command sentence input (e.g. *"Close Calculator and volume up"*). The multi-command engine parses compound sentences, executes sub-commands sequentially, and synthesizes a single concise summary response.

---

## Execution Pipeline

1. **Clause Splitting (`core/command_normalizer.py`)**:
   Splits compound phrases by conjunctions (`and`, `then`, `,`).
   - Example Input: `"Close Calculator and volume up"`
   - Sub-command 1: `"close calculator"`
   - Sub-command 2: `"volume up"`

2. **Sequential Execution (`core/jarvis_runtime.py`)**:
   Executes sub-commands one by one without speaking after each individual action.

3. **Concatenated Response Synthesis (`core/local_response_engine.py`)**:
   Combines sub-command results into one clean spoken summary:
   - Output: `"Done. Closing Calculator., and Volume increased."`
