import logging
import psutil
from pathlib import Path
from config import config
from modules.system import app_control, window_control, system_control, screenshot, permissions
from modules.files import file_control
from modules.browser import web_control
from core.os import TerminalManager, FilesystemManager, ProcessManager, SystemInfoProvider, ProjectRegistry, BrowserManager

logger = logging.getLogger("Jarvis.Executor")

class CommandExecutor:
    """Central command execution engine.
    Validates, routes, and executes system commands, web links, system info requests, maintaining permission checks.
    Returns standardized execution output dictionaries.
    """

    def __init__(self, history_tracker=None):
        self.history_tracker = history_tracker
        self.terminal_mgr = TerminalManager()
        self.filesystem_mgr = FilesystemManager()
        self.process_mgr = ProcessManager()
        self.system_info_mgr = SystemInfoProvider()
        self.project_registry = ProjectRegistry()
        self.browser_mgr = BrowserManager()
        logger.info("Command Executor initialized with Full OS Control Layer.")

    def execute(self, intent_node: dict, confirm: bool = False) -> dict:
        """Executes a structured intent node command.

        Args:
            intent_node: Dictionary containing 'intent', 'action', 'target', or 'query'
            confirm: Boolean flag indicating if high-risk actions have been confirmed by user

        Returns:
            Dictionary representing structured execution results:
            {
                "success": bool,
                "message": str,
                "intent": str,
                "action": str,
                "target": str,
                "spoken": bool,
                "pending_confirmation": bool
            }
        """
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action") or intent
        target = intent_node.get("target")

        logger.info(f"Executor received command: Intent='{intent}', Action='{action}', Target='{target}'")

        # 1. Validate Command Parameters for safety
        if not permissions.is_safe_command(intent, intent_node):
            result = {
                "success": False,
                "message": "Action blocked: Command contains forbidden shell metacharacters.",
                "intent": intent,
                "action": action,
                "target": target,
                "spoken": True,
                "pending_confirmation": False
            }
            self._record_history(intent_node, result)
            return result

        # 2. Risk and Permission Level Check
        risk_level = permissions.get_action_risk_level(intent, action)
        logger.info(f"Action safety classification: {risk_level}")

        if risk_level == permissions.RiskLevel.HIGH and not confirm:
            logger.info("High-risk action blocked. Awaiting user confirmation.")
            result = {
                "success": False,
                "message": "This action is high risk. Are you sure you want to proceed?",
                "intent": intent,
                "action": action,
                "target": target,
                "spoken": True,
                "pending_confirmation": True
            }
            return result

        # 3. Route Command to appropriate modules
        success = False
        message = ""

        try:
            if intent == "open_website":
                success, message = web_control.open_website(target)

            elif intent == "web_search":
                provider = intent_node.get("provider", "google")
                query = intent_node.get("target") or intent_node.get("query", "")
                res = self.browser_mgr.search(query, provider=provider)
                success = res["success"]
                message = res["message"]

            elif intent == "time_query":
                import datetime
                now = datetime.datetime.now()
                success = True
                message = f"The time is {now.strftime('%I:%M %p')}."

            elif intent == "date_query":
                import datetime
                now = datetime.datetime.now()
                success = True
                message = f"Today is {now.strftime('%A, %B %d, %Y')}."

            elif intent == "math_calculation":
                import re, math
                query_str = target or intent_node.get("query", "")
                q = query_str.lower()
                q = re.sub(r'^(calculate|what is|how much is|solve|math)\s+', '', q).strip(' ?')
                pct_match = re.search(r'([\d\.]+)\s*(?:%|percent)\s*(?:of)\s*([\d\.]+)', q)
                if pct_match:
                    val = (float(pct_match.group(1)) / 100.0) * float(pct_match.group(2))
                    success = True
                    message = f"{pct_match.group(1)} percent of {pct_match.group(2)} is {val:g}."
                else:
                    try:
                        q = re.sub(r'([\d\.]+)\s*(?:to the power of|\^)\s*([\d\.]+)', r'math.pow(\1, \2)', q)
                        q = re.sub(r'(?:square root of|sqrt)\s*([\d\.]+)', r'math.sqrt(\1)', q)
                        q = q.replace(' multiplied by ', ' * ').replace(' times ', ' * ').replace(' x ', ' * ')
                        q = q.replace(' divided by ', ' / ').replace(' plus ', ' + ').replace(' minus ', ' - ')
                        allowed_names = {'math': math, 'sqrt': math.sqrt, 'pow': math.pow, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'pi': math.pi}
                        clean_expr = re.sub(r'[^0-9\+\-\*\/\(\)\.\s\,a-zA-Z_]', '', q)
                        res_val = eval(clean_expr, {'__builtins__': {}}, allowed_names)
                        success = True
                        message = f"The result is {res_val:g}."
                    except Exception as calc_err:
                        logger.warning(f"Math calculation failed: {calc_err}")
                        success = False
                        message = "I couldn't calculate that math expression."

            elif intent == "media_control":
                import ctypes
                VK_MEDIA_NEXT_TRACK = 0xB0
                VK_MEDIA_PREV_TRACK = 0xB1
                VK_MEDIA_STOP = 0xB2
                VK_MEDIA_PLAY_PAUSE = 0xB3

                if action == "next_track":
                    vk = VK_MEDIA_NEXT_TRACK
                    msg_text = "Skipped to next track."
                elif action == "previous_track":
                    vk = VK_MEDIA_PREV_TRACK
                    msg_text = "Returned to previous track."
                elif action == "stop":
                    vk = VK_MEDIA_STOP
                    msg_text = "Media playback stopped."
                else:
                    vk = VK_MEDIA_PLAY_PAUSE
                    msg_text = "Media playback toggled."

                try:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                    success = True
                    message = msg_text
                except Exception as m_err:
                    logger.error(f"Media key error: {m_err}")
                    success = False
                    message = "Failed to send media control command."

            elif intent == "test_speech":
                success = True
                message = "Speech synthesis is active and operational."

            elif intent == "test_microphone":
                from core.listener import SpeechListener
                listener = SpeechListener()
                diag = listener.run_microphone_diagnostics()
                success = True
                message = diag.get("spoken_summary", "Microphone test completed.")

            elif intent == "open_app":
                if not target:
                    message = "No application specified."
                else:
                    success = app_control.open_app(target)
                    message = f"Launched {target} successfully." if success else f"Failed to launch {target}."

            elif intent == "close_app":
                if not target:
                    message = "No application specified to close."
                else:
                    success = app_control.close_app(target)
                    message = f"Closed {target} successfully." if success else f"Failed to close {target} (maybe not running)."

            elif intent == "window_control":
                success, message = self._handle_window_control(action, target)

            elif intent == "file_access":
                success, message = self._handle_file_access(action, target)

            elif intent == "terminal_execute":
                cwd = self.project_registry.get_current_project()["path"]
                if action == "check_port":
                    port_num = int(target) if str(target).isdigit() else 5000
                    p_info = self.process_mgr.get_port_process(port_num)
                    if p_info:
                        success = True
                        message = f"Port {port_num} is used by process {p_info['name']} (PID {p_info['pid']})."
                    else:
                        success = True
                        message = f"Port {port_num} is currently free."
                elif action == "node_processes":
                    procs = self.process_mgr.find_process("node")
                    if procs:
                        success = True
                        p_list = ", ".join([f"{p['name']} (PID {p['pid']})" for p in procs])
                        message = f"Running Node processes: {p_list}."
                    else:
                        success = True
                        message = "No running Node processes found."
                else:
                    res = self.terminal_mgr.execute(target, cwd=cwd)
                    success = res["success"]
                    output = res["stdout"] or res["stderr"] or "Command completed."
                    if len(output) > 150:
                        message = "I found the output. I've displayed it in the Jarvis interface."
                    else:
                        message = f"Command output: {output}"

            elif intent == "system_telemetry":
                if action == "cpu_info":
                    res = self.system_info_mgr.get_cpu_info()
                elif action == "ram_info":
                    res = self.system_info_mgr.get_ram_info()
                elif action == "disk_info":
                    res = self.system_info_mgr.get_disk_info()
                elif action == "os_info":
                    res = self.system_info_mgr.get_os_info()
                elif action == "ip_info":
                    res = self.system_info_mgr.get_network_ip()
                elif action == "uptime_info":
                    res = self.system_info_mgr.get_uptime()
                else:
                    res = self.system_info_mgr.get_cpu_info()
                success = res["success"]
                message = res["text"]

            elif intent == "project_control":
                success = self.project_registry.set_current_project(target)
                proj = self.project_registry.get_current_project()
                message = f"Switched project context to {proj['alias'].title()}." if success else f"Could not find project '{target}'."

            elif intent == "filesystem_control":
                cwd = self.project_registry.get_current_project()["path"]
                if action == "list_directory":
                    res = self.filesystem_mgr.list_directory(cwd)
                    success = res["success"]
                    if success:
                        files_str = ", ".join([item["name"] for item in res["items"][:5]])
                        message = f"Found {res['count']} items in {Path(cwd).name}: {files_str}."
                    else:
                        message = res.get("error", "Could not list directory.")

            elif intent == "screenshot":
                if action == "open_folder":
                    success = screenshot.open_screenshot_folder()
                    message = "Opening screenshots folder." if success else "Failed to open screenshots folder."
                else:
                    success, message = screenshot.take_screenshot()

            elif intent in ["system_control", "status_request", "system_action"]:
                success, message = self._handle_system_control(action, target)

            elif intent == "identity":
                success = True
                owner = getattr(config, "owner_name", "Active Gamer")
                name = getattr(config, "assistant_name", "Jarvis")
                message = f"I am {name}, your personal AI desktop assistant. I was designed and built by {owner} as a long-term personal AI operating system."

            elif intent == "help":
                success = True
                message = (
                    "Goliya can control applications, manage your computer, open files and websites, take screenshots, answer questions, and execute multiple commands.\n"
                    "• Applications: Open Chrome, Open VS Code, Open Steam, Open Downloads\n"
                    "• System: Volume up, Lock PC, Screenshot, Resource Metrics\n"
                    "Examples: Open Chrome, Open Downloads, Volume up, Take a screenshot, or Open Chrome and VS Code."
                )

            elif intent == "about":
                success = True
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                name = getattr(config, 'assistant_name', 'Jarvis')
                version = getattr(config, 'version', '1.1')
                owner = getattr(config, 'owner_name', 'Active Gamer')
                whisper_size = getattr(config, 'whisper_model_size', 'small')
                tts_voice = getattr(config, 'model_tts_voice', 'en-US-GuyNeural')
                llm_status = "Online" if config.gemini_api_key else "Offline Mode"

                message = (
                    f"{name} Assistant Version {version}\n"
                    f"Developer / Owner: {owner}\n"
                    f"Whisper Speech Model: {whisper_size}\n"
                    f"TTS Voice Engine: {tts_voice}\n"
                    f"LLM Cognitive Engine: {llm_status}\n"
                    f"OS Control Status: Operational\n"
                    f"CPU Usage: {cpu}%\n"
                    f"RAM Usage: {ram}%"
                )

            elif intent == "history_query":
                if self.history_tracker and self.history_tracker.get_history():
                    last_record = self.history_tracker.get_history()[-1]
                    cmd = last_record.get('command', 'Unknown')
                    res = last_record.get('result', 'Executed')
                    success = True
                    message = f"Your last command was: '{cmd}'. Result: {res}"
                else:
                    success = True
                    message = "No previous commands recorded in this session."

            else:
                message = f"Unknown or unexecutable intent: {intent}"

        except Exception as e:
            logger.error(f"Execution failed with error: {e}", exc_info=True)
            success = False
            message = "I couldn't complete that request."

        result = {
            "success": success,
            "message": message,
            "intent": intent,
            "action": action,
            "target": target,
            "spoken": True,
            "pending_confirmation": False
        }

        # 4. Record Action in History
        self._record_history(intent_node, result)
        return result

    def _handle_window_control(self, action: str, target: str) -> (bool, str):
        if action == "minimize":
            success = window_control.minimize_window(target)
            return success, "Window minimized." if success else "Failed to minimize window."
        elif action == "maximize":
            success = window_control.maximize_window(target)
            return success, "Window maximized." if success else "Failed to maximize window."
        elif action == "restore":
            success = window_control.restore_window(target)
            return success, "Window restored." if success else "Failed to restore window."
        elif action in ["switch", "focus"]:
            if not target:
                return False, "No target window specified to switch to."
            success = window_control.switch_to_window(target)
            return success, f"Switched to {target}." if success else f"Failed to find window matching '{target}'."
        elif action == "close":
            success = window_control.close_window(target)
            return success, "Closed window." if success else "Failed to close window."
        elif action in ["list", "list_open"]:
            titles = window_control.list_open_windows()
            if not titles:
                return True, "No open windows detected."
            msg_list = ", ".join(titles[:5])
            if len(titles) > 5:
                msg_list += f" and {len(titles)-5} more"
            return True, f"Open windows: {msg_list}."
        else:
            return False, f"Unknown window control action: {action}"

    def _handle_file_access(self, action: str, target: str) -> (bool, str):
        if action == "open_folder":
            if not target:
                return False, "No folder target specified."
            success = file_control.open_folder(target)
            return success, f"Opened {target} folder." if success else f"Failed to open {target}."
        elif action == "open_file":
            if not target:
                return False, "No file path specified."
            success = file_control.open_file(target)
            return success, f"Opened file {target}." if success else "Failed to open file."
        elif action == "search_file":
            if not target:
                return False, "No search term specified."
            matches = file_control.search_files(target)
            if not matches:
                return True, f"No matching files found for '{target}'."
            names = [Path(m).name for m in matches[:3]]
            msg = f"Found matches: {', '.join(names)}"
            if len(matches) > 3:
                msg += f" (and {len(matches)-3} more)"
            return True, msg
        else:
            return False, f"Unknown file control action: {action}"

    def _handle_system_control(self, action: str, target: str) -> (bool, str):
        if action == "volume_up":
            return system_control.volume_up()
        elif action == "volume_down":
            return system_control.volume_down()
        elif action == "mute":
            return system_control.mute_volume()
        elif action == "unmute":
            return system_control.unmute_volume()
        elif action in ["lock", "lock_pc"]:
            return system_control.lock_pc()
        elif action in ["sleep", "sleep_pc"]:
            return system_control.sleep_pc()
        elif action in ["restart", "restart_pc"]:
            return system_control.restart_pc()
        elif action in ["shutdown", "shutdown_pc"]:
            return system_control.shutdown_pc()
        elif action == "battery":
            return system_control.get_battery_status()
        elif action in ["cpu", "ram", "disk", "metrics"]:
            success, metrics = system_control.get_system_metrics()
            if success:
                return True, metrics["message"]
            return False, "Failed to retrieve system resource metrics."
        else:
            return False, f"Unknown system control action: {action}"

    def _record_history(self, intent_node: dict, result: dict):
        if self.history_tracker:
            try:
                self.history_tracker.add_action(
                    command=intent_node.get("query", "Voice command"),
                    intent=intent_node.get("intent", "unknown"),
                    result=result.get("message", "Executed"),
                    success=result.get("success", False)
                )
            except Exception as e:
                logger.error(f"Failed to record action history: {e}")
