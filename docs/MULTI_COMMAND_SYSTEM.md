# Multi-Command System — Project Goliya

## Overview
Goliya supports parsing and executing multiple commands within a single spoken or typed sentence. The `MultiCommandParser` splits compound queries into sequential single command nodes that execute independently.

---

## Separators & Clause Processing
The `MultiCommandParser` recognizes the following conjunctions and delimiters:
- `and`
- `then`
- `also`
- `after that`
- `,` (comma)

---

## Clause Parsing & Verb Propagation Examples

### Example 1: Action Conjunction
**Input**: `"Open Chrome, then open GitHub and increase volume."`
1. Clause 1: `"Open Chrome"` -> Intent: `open_app` (target: `chrome`)
2. Clause 2: `"open GitHub"` -> Intent: `open_website` (target: `github`)
3. Clause 3: `"increase volume"` -> Intent: `system_control` (action: `volume_up`)

---

### Example 2: Entity Verb Propagation
**Input**: `"Open Chrome and VS Code."`
- First clause contains verb `"open"` and entity `"Chrome"`.
- Second clause `"VS Code"` inherits verb `"open"`.
1. Sub-command 1: `"open Chrome"` -> Intent: `open_app` (target: `chrome`)
2. Sub-command 2: `"open VS Code"` -> Intent: `open_app` (target: `vscode`)

---

### Example 3: System & Media Commands
**Input**: `"Take a screenshot and open Downloads."`
1. Sub-command 1: `"Take a screenshot"` -> Intent: `screenshot` (action: `take_screenshot`)
2. Sub-command 2: `"open Downloads"` -> Intent: `file_access` (action: `open_folder`, target: `downloads`)

---

## Sequential Pipeline Routing Flow
Each sub-command independently passes through the pipeline:
```
Sub-Command 1 ──► Normalizer ──► Intent Engine ──► OS Executor ──► Response Manager
                                                                         │
                                                                         ▼
Sub-Command 2 ──► Normalizer ──► Intent Engine ──► OS Executor ──► Response Manager
```
