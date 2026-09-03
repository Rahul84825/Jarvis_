# OS Security & Permissions Architecture

## Overview
Jarvis is engineered to operate safely within the standard permission boundaries of the active user account without requesting unnecessary root/administrator privileges or bypassing operating system security controls.

---

## Key Security Principles

1. **Standard User Privilege Scope**: Jarvis runs under the permissions of the current logged-in user account.
2. **Standard Elevation Requests**: If an action requires elevated privileges (e.g. system service configuration), Jarvis informs the user and delegates to native OS elevation mechanisms (Windows UAC / Linux sudo).
3. **Secret Redaction**: Passwords, API keys, access tokens, and `.env` credentials are automatically redacted from console outputs, logs, and spoken audio.
4. **Sanitized Error Responses**: Raw Python tracebacks (`PermissionError`, `AccessDenied`) are caught and converted to polite spoken responses (*"I don't have permission to access that location."*).
5. **No Dangerous Command Inference**: Vague inputs will not execute destructive shell commands.
