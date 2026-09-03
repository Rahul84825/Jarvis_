# Offline Response System — Project Goliya

## Overview
The Offline Response System ensures Goliya operates seamlessly without exposing technical API configuration errors to the user.

---

## Zero API Error Exposure Rule
Users will **NEVER** hear or see messages such as:
- *"Gemini API key is missing."*
- *"Please configure your API key."*
- *"Gemini API is not configured."*
- *"API key required."*
- *"Configure config.py."*

All technical API errors, missing credentials, or network failures are written strictly to developer logs (`logs/jarvis.log`).

---

## Response Routing Flowchart

```
                 User Voice / Text Command
                             │
                             ▼
                    Command Normalizer
                             │
                             ▼
                       Intent Engine
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   Local System / OS Command          Cognitive / General Question
   ("Open Chrome", "Volume Up",       ("Explain quantum computing")
    "Take screenshot", "Help")                │
            │                                 ▼
            ▼                       Gemini API Configured & Online?
    Local Execution                         │
            │                         ┌─────┴─────┐
            ▼                         ▼           ▼
    Local Response                   Yes          No
   ("Opening Chrome",                 │           │
    "Volume increased")               ▼           ▼
                                   Gemini    Local Offline Fallback
                                  Response   ("I'm currently operating in
                                             offline mode...")
```

---

## Local Offline Commands & Responses

| User Query / Command | Backend Used | Spoken Response |
| :--- | :--- | :--- |
| `"Open Chrome"` | Local OS Executor | *"Opening Chrome."* |
| `"Take a screenshot"` | Local OS Executor | *"Screenshot saved."* |
| `"Volume up"` | Local OS Executor | *"Volume increased."* |
| `"Lock computer"` | Local OS Executor | *"Computer locked successfully."* |
| `"Open Downloads"` | Local OS Executor | *"Opened downloads folder."* |
| `"Who are you?"` | Local Response System | *"I'm Goliya, your personal desktop AI assistant."* |
| `"Help"` | Local Response System | *"Goliya can control applications, manage your computer, open files..."* |
| `"Explain quantum computing"` (No API key) | Local Offline Fallback | *"I'm currently operating in offline mode, so I can't provide my full AI response for that question right now."* |
