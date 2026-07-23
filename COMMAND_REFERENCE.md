# JARVIS COMMAND REFERENCE
## WEEK 3 VOICE CONTROL CATALOGUE

Below is the exhaustive list of supported voice commands, categorized by function, risk level, and intent. Jarvis parses these using deterministic regular expressions and string matching in `core/intent_engine.py` for maximum speed and reliability.

---

## 1. Application Control

These commands control launching and closing common applications.

| Command Phrase | Intent | Action | Expected Behavior | Risk Level |
| :--- | :--- | :--- | :--- | :--- |
| **"Open Chrome"** / **"Launch Chrome"** | `open_app` | *launch* | Opens Google Chrome. If already running, brings the window to focus. | **LOW** |
| **"Open Edge"** / **"Launch Edge"** | `open_app` | *launch* | Opens Microsoft Edge. If already running, focuses the window. | **LOW** |
| **"Open Firefox"** / **"Launch Firefox"** | `open_app` | *launch* | Opens Mozilla Firefox. If already running, focuses the window. | **LOW** |
| **"Open VS Code"** / **"Launch VS Code"** | `open_app` | *launch* | Opens Visual Studio Code. If already running, focuses the window. | **LOW** |
| **"Open Notepad"** / **"Launch Notepad"** | `open_app` | *launch* | Opens a new instance of Notepad. | **LOW** |
| **"Open Calculator"** / **"Launch Calculator"** | `open_app` | *launch* | Opens a new instance of Windows Calculator. | **LOW** |
| **"Open Explorer"** / **"Launch Explorer"** | `open_app` | *launch* | Opens a new File Explorer window. | **LOW** |
| **"Open Spotify"** / **"Launch Spotify"** | `open_app` | *launch* | Opens Spotify. If already running, focuses the window. | **LOW** |
| **"Open Discord"** / **"Launch Discord"** | `open_app` | *launch* | Opens Discord. If already running, focuses the window. | **LOW** |
| **"Open Steam"** / **"Launch Steam"** | `open_app` | *launch* | Opens Steam. If already running, focuses the window. | **LOW** |
| **"Close Chrome"** / **"Exit Chrome"** | `close_app` | *terminate* | Terminates all running Google Chrome processes. | **MEDIUM** |
| **"Close Edge"** / **"Exit Edge"** | `close_app` | *terminate* | Terminates all running Microsoft Edge processes. | **MEDIUM** |
| **"Close Firefox"** / **"Exit Firefox"** | `close_app` | *terminate* | Terminates all running Mozilla Firefox processes. | **MEDIUM** |
| **"Close VS Code"** / **"Exit VS Code"** | `close_app` | *terminate* | Terminates all running Visual Studio Code processes. | **MEDIUM** |
| **"Close Notepad"** / **"Exit Notepad"** | `close_app` | *terminate* | Terminates all running Notepad processes. | **MEDIUM** |
| **"Close Calculator"** / **"Exit Calculator"** | `close_app` | *terminate* | Terminates all running Calculator processes. | **MEDIUM** |
| **"Close Explorer"** / **"Exit Explorer"** | `close_app` | *terminate* | *Blocked for safety.* (Does not terminate the Windows Shell). | **MEDIUM** (Blocked) |
| **"Close Spotify"** / **"Exit Spotify"** | `close_app` | *terminate* | Terminates all running Spotify processes. | **MEDIUM** |
| **"Close Discord"** / **"Exit Discord"** | `close_app` | *terminate* | Terminates all running Discord processes. | **MEDIUM** |
| **"Close Steam"** / **"Exit Steam"** | `close_app` | *terminate* | Terminates all running Steam processes. | **MEDIUM** |

---

## 2. Window Management

These commands manipulate active windows or look up windows by matching title names.

| Command Phrase | Intent | Action | Expected Behavior | Risk Level |
| :--- | :--- | :--- | :--- | :--- |
| **"Minimize Chrome"** | `window_control` | `minimize` | Minimizes the first window matching "Chrome". | **MEDIUM** |
| **"Minimize active window"** / **"Minimize window"** | `window_control` | `minimize` | Minimizes the currently focused/active window. | **MEDIUM** |
| **"Maximize VS Code"** | `window_control` | `maximize` | Maximizes the first window matching "VS Code". | **MEDIUM** |
| **"Maximize active window"** / **"Maximize window"** | `window_control` | `maximize` | Maximizes the currently focused/active window. | **MEDIUM** |
| **"Restore Notepad"** | `window_control` | `restore` | Restores the Notepad window from minimized/maximized state. | **MEDIUM** |
| **"Switch to Spotify"** / **"Focus Spotify"** | `window_control` | `switch` | Restores and focuses Spotify window to foreground. | **MEDIUM** |
| **"Switch to VS Code"** / **"Focus VS Code"** | `window_control` | `switch` | Restores and focuses VS Code window to foreground. | **MEDIUM** |
| **"Close current window"** / **"Close active window"** | `window_control` | `close` | Closes the currently active window. | **MEDIUM** |
| **"List open windows"** / **"List windows"** | `window_control` | `list_open` | Reads aloud and logs titles of the first 5 visible windows. | **MEDIUM** |

---

## 3. File System Control (Read-Only)

These commands let you open specific directories or search for files.

| Command Phrase | Intent | Action | Expected Behavior | Risk Level |
| :--- | :--- | :--- | :--- | :--- |
| **"Open Downloads"** / **"Go to Downloads"** | `file_access` | `open_folder` | Opens `C:\Users\<user>\Downloads` in File Explorer. | **MEDIUM** |
| **"Open my Documents"** / **"Open Documents"** | `file_access` | `open_folder` | Opens `C:\Users\<user>\Documents` in File Explorer. | **MEDIUM** |
| **"Open Desktop"** / **"Go to Desktop"** | `file_access` | `open_folder` | Opens `C:\Users\<user>\Desktop` in File Explorer. | **MEDIUM** |
| **"Open project folder"** / **"Open workspace"** | `file_access` | `open_folder` | Opens Jarvis workspace directory in File Explorer. | **MEDIUM** |
| **"Find resume.pdf"** / **"Search for resume.pdf"** | `file_access` | `search_file` | Traverses user directories to find files matching `resume.pdf`. | **MEDIUM** |
| **"Find project_doc.docx"** | `file_access` | `search_file` | Traverses user folders for file matching `project_doc.docx`. | **MEDIUM** |

---

## 4. System Control & Power

These commands control volume, lock status, system power actions, and telemetry data.

| Command Phrase | Intent | Action | Expected Behavior | Risk Level | Safety Confirmation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **"Increase volume"** / **"Volume Up"** | `system_control` | `volume_up` | Increases Master Volume by 10%. | **MEDIUM** | No |
| **"Decrease volume"** / **"Volume Down"** | `system_control` | `volume_down` | Decreases Master Volume by 10%. | **MEDIUM** | No |
| **"Mute volume"** / **"Mute"** | `system_control` | `mute` | Mutes master volume. | **MEDIUM** | No |
| **"Unmute volume"** / **"Unmute"** | `system_control` | `unmute` | Unmutes master volume. | **MEDIUM** | No |
| **"Lock my computer"** / **"Lock screen"** | `system_control` | `lock` | Instantly locks the computer screen. | **MEDIUM** | No |
| **"Sleep my computer"** / **"Sleep computer"** | `system_control` | `sleep` | Puts the Windows PC to sleep. | **HIGH** | **Yes** (Voice/HUD) |
| **"Restart the PC"** / **"Reboot computer"** | `system_control` | `restart` | Initiates immediate reboot. | **HIGH** | **Yes** (Voice/HUD) |
| **"Shutdown the PC"** / **"Turn off computer"** | `system_control` | `shutdown` | Initiates immediate shutdown. | **HIGH** | **Yes** (Voice/HUD) |
| **"Battery status"** / **"Check battery"** | `status_request` | `battery` | Reports remaining battery percent. | **MEDIUM** | No |
| **"CPU usage"** / **"Check system status"** | `status_request` | `metrics` | Reports current CPU, RAM, and Disk usage. | **MEDIUM** | No |

---

## 5. Screenshot System

These commands allow taking screenshots and opening the destination folder.

| Command Phrase | Intent | Action | Expected Behavior | Risk Level |
| :--- | :--- | :--- | :--- | :--- |
| **"Take a screenshot"** / **"Take screenshot"** | `screenshot` | `take_screenshot` | Saves a full-screen timestamped PNG under `screenshots/`. | **MEDIUM** |
| **"Show screenshots"** / **"Open screenshot folder"** | `screenshot` | `open_folder` | Opens the local `screenshots/` directory in File Explorer. | **MEDIUM** |

---

## 6. Physical Micro-interactions

These acoustic gestures trigger background actions.

| Input Gesture | Action Triggered | Target Subsystem | Expected Behavior |
| :--- | :--- | :--- | :--- |
| **Single Clap** | System Ping | Speaker / TTS | Jarvis outputs sound cue *"Ping acknowledged"* to signify status is alive. |
| **Double Clap** | Privacy Toggle | VAD & Microphone | Toggles privacy mute status (disables/enables speech listening threads). |
