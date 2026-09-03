# JARVIS ASSISTANT - COMMAND REFERENCE MANUAL (v1.1)

This document provides a comprehensive command reference for **Jarvis AI Desktop Assistant**.

---

## 1. Wake Words & Greetings

Primary Wake Word: **`Jarvis`**

Supported Wake Phrases & Greetings:
- *"Jarvis"*
- *"Hey Jarvis"*
- *"Hello Jarvis"*
- *"Hi Jarvis"*
- *"Namaste Jarvis"*
- *"Good morning Jarvis"*
- *"Good evening Jarvis"*
- *"Good afternoon Jarvis"*
- *"Yo Jarvis"*
- *"Hey buddy"*

---

## 2. Conversation, Identity & Help Commands

| Query / Command | Intent | Description |
| :--- | :--- | :--- |
| *"Who are you?"*, *"Who created you?"*, *"Who built you?"*, *"Who owns you?"* | `identity` | Speaks and displays Jarvis assistant identity and owner/developer (*Active Gamer*). |
| *"Help"*, *"Help me"*, *"What can you do"*, *"Show commands"*, *"Capabilities"* | `help` | Categorized capabilities summary (Applications, System, Conversation, Future Features). |
| *"About"*, *"About Jarvis"*, *"Version"*, *"System Info"* | `about` | Displays Version `v1.1`, Developer, Whisper model size, TTS voice, CPU % and RAM %. |
| *"What was my last command?"*, *"Repeat last command"*, *"Show history"* | `history_query` | Reads out the last executed command and its execution result. |
| *"Repeat"*, *"What did you say?"* | `repeat_response` | Re-speaks the exact last output spoken by Jarvis. |

---

## 3. Web Links Commands (`config/links.json`)

| Voice Command | Action Target | Web URL |
| :--- | :--- | :--- |
| *"Open YouTube"* | `youtube` | `https://www.youtube.com` |
| *"Open Google"* | `google` | `https://www.google.com` |
| *"Open GitHub"* | `github` | `https://www.github.com` |
| *"Open Gmail"* | `gmail` | `https://mail.google.com` |
| *"Open ChatGPT"* | `chatgpt` | `https://chatgpt.com` |
| *"Open Claude"* | `claude` | `https://claude.ai` |
| *"Open Gemini"* | `gemini` | `https://gemini.google.com` |
| *"Open Spotify"* | `spotify` | `https://open.spotify.com` |
| *"Open Netflix"* | `netflix` | `https://www.netflix.com` |
| *"Open Prime Video"* | `prime video` | `https://www.primevideo.com` |
| *"Open Discord"* | `discord` | `https://discord.com/app` |
| *"Open Reddit"* | `reddit` | `https://www.reddit.com` |
| *"Open Stack Overflow"* | `stackoverflow` | `https://stackoverflow.com` |
| *"Open LinkedIn"* | `linkedin` | `https://www.linkedin.com` |
| *"Open Instagram"* | `instagram` | `https://www.instagram.com` |
| *"Open Facebook"* | `facebook` | `https://www.facebook.com` |
| *"Open X"* / *"Open Twitter"* | `x` | `https://x.com` |
| *"Open WhatsApp Web"* | `whatsapp` | `https://web.whatsapp.com` |
| *"Open Google Drive"* | `drive` | `https://drive.google.com` |
| *"Open Google Calendar"* | `calendar` | `https://calendar.google.com` |

---

## 4. System Control & Power Commands

| Voice Command | Intent / Sub-Action | Action Details |
| :--- | :--- | :--- |
| *"Lock PC"*, *"Lock computer"*, *"Lock"* | `system_control:lock_pc` | Locks current Windows user session immediately. |
| *"Sleep computer"*, *"Sleep PC"* | `system_control:sleep_pc` | Puts workstation into sleep state (Safety confirmation required). |
| *"Shutdown computer"*, *"Shutdown PC"* | `system_control:shutdown_pc` | Initiates system power off (Safety confirmation required). |
| *"Restart computer"*, *"Restart PC"* | `system_control:restart_pc` | Restarts computer (Safety confirmation required). |
| *"Volume up"*, *"Increase volume"* | `system_control:volume_up` | Increases master Windows audio volume by 10%. |
| *"Volume down"*, *"Decrease volume"* | `system_control:volume_down` | Decreases master Windows audio volume by 10%. |
| *"Mute"*, *"Mute volume"* | `system_control:mute` | Mutes system audio output. |
| *"Unmute"*, *"Unmute volume"* | `system_control:unmute` | Unmutes system audio output. |
| *"Take screenshot"*, *"Screenshot"* | `screenshot:take_screenshot` | Captures primary monitor and saves PNG image to `screenshots/`. |
| *"Open downloads"* | `file_access:open_folder` | Opens user Downloads directory in File Explorer. |

---

## 5. Multi-Command Execution (Chaining)

Commands can be chained in natural speech using `and`, `then`, `after that`, `also`, `,`.

Examples:
- *"Open Chrome and VS Code"* $\rightarrow$ Opens Chrome, then opens VS Code.
- *"Take Screenshot and Open Downloads"* $\rightarrow$ Takes a screenshot, then opens the Downloads folder.
- *"Open Chrome, Open GitHub and Open Downloads"* $\rightarrow$ Opens Chrome, opens GitHub website, opens Downloads folder.

---

## 6. Fuzzy Shorthand Matching

| Shorthand Input | Expanded Command | Action Executed |
| :--- | :--- | :--- |
| *"Chrome"* | `Open Chrome` | Launches Google Chrome |
| *"VS"* | `Open VS Code` | Launches Visual Studio Code |
| *"Screenshot"* | `Take Screenshot` | Captures screen image |
| *"Downloads"* | `Open Downloads` | Opens Downloads folder |
| *"Lock"* | `Lock computer` | Locks Windows session |
