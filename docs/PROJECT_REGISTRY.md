# Project Registry & Context Architecture

## Overview
The Project Registry (`core/os/project_registry.py`) maps project aliases to local project directories via `config/projects.json` and maintains active project working context across user voice commands.

---

## Configuration Schema (`config/projects.json`)

```json
{
  "jarvis": "c:\\Users\\activ\\OneDrive\\Attachments\\Desktop\\jarvis",
  "wellmeds": "c:\\Projects\\WellMeds"
}
```

---

## Context-Aware Command Execution

When a user switches projects (e.g., *"Open my Jarvis project"*), `ProjectRegistry` sets the active context to `"jarvis"`.
Subsequent commands (e.g., *"Run git status"*, *"List files"*, *"Open package.json"*) automatically execute relative to the active project context without requiring the user to repeat absolute paths.
