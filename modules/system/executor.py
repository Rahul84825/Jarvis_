import os
import time
import logging
import psutil
from pathlib import Path
from config import config
from modules.system import app_control, window_control, system_control, screenshot, permissions
from modules.files import file_control
from modules.browser import web_control
from core.os import TerminalManager, FilesystemManager, ProcessManager, SystemInfoProvider, ProjectRegistry, BrowserManager
from core.content_generator import ContentGenerator
from core.response_registry import CommandOutcome

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
        self.content_gen = ContentGenerator(filesystem_mgr=self.filesystem_mgr)
        self.last_created_file = None
        self.last_search_results = []
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
        t0 = time.time()

        logger.info(f"Executor received command: Intent='{intent}', Action='{action}', Target='{target}'")

        # 1. Validate Command Parameters for safety
        if not permissions.is_safe_command(intent, intent_node):
            result = {
                "success": False,
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
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
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
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
        outcome = None

        try:
            if intent == "open_website":
                success, message = web_control.open_website(target)
                if not success:
                    outcome = CommandOutcome.EXECUTION_FAILED
                    message = "I couldn't open that website, Sir."
                else:
                    outcome = CommandOutcome.SUCCESS

            elif intent == "web_search":
                provider = intent_node.get("provider", "google")
                query = intent_node.get("target") or intent_node.get("query", "")
                empty_q = intent_node.get("empty_query", False) or not query or not query.strip()

                if empty_q:
                    logger.info("[SEARCH] Empty search query detected. Prompting clarification.")
                    logger.info("[SEARCH] Tool execution completed")
                    msg = "What would you like me to search for, Sir?"
                    logger.info(f"[SEARCH] Response generation completed: '{msg}'")
                    result = {
                        "success": True,
                        "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                        "message": msg,
                        "intent": "web_search",
                        "action": "search",
                        "target": "",
                        "spoken": True,
                        "pending_confirmation": False
                    }
                    self._record_history(intent_node, result)
                    return result

                logger.info("[SEARCH] Tool execution started")
                try:
                    res = self.browser_mgr.search(query, provider=provider)
                    success = bool(res.get("success", False))
                    message = res.get("message", "")
                    if success:
                        outcome = CommandOutcome.SUCCESS
                        logger.info("[SEARCH] Tool execution completed")
                        logger.info(f"[SEARCH] Results received: 1 (Browser search launched: {provider})")
                        logger.info(f"[SEARCH] Response generation completed: '{message}'")
                    else:
                        err_detail = res.get("message", "")
                        if "not configured" in err_detail.lower():
                            outcome = CommandOutcome.PROVIDER_UNAVAILABLE
                            message = err_detail or "Search is temporarily unavailable, Sir."
                        elif "timed out" in err_detail.lower() or "timeout" in err_detail.lower():
                            outcome = CommandOutcome.TIMEOUT
                            message = err_detail or "That action timed out, Sir. Please try again."
                        elif "network" in err_detail.lower() or "connection" in err_detail.lower() or "unavailable" in err_detail.lower():
                            outcome = CommandOutcome.PROVIDER_UNAVAILABLE
                            message = err_detail or "Search is temporarily unavailable, Sir."
                        else:
                            outcome = CommandOutcome.EXECUTION_FAILED
                            message = err_detail or "That action failed, Sir. Please try again."
                        logger.error(f"[SEARCH] Execution failed: {message}")
                except TimeoutError as te:
                    success = False
                    outcome = CommandOutcome.TIMEOUT
                    message = "That action timed out, Sir. Please try again."
                    logger.error(f"[SEARCH] Execution failed: {te}")
                    logger.error("[SEARCH] Failure category: timeout")
                except Exception as e:
                    success = False
                    outcome = CommandOutcome.PROVIDER_UNAVAILABLE
                    message = "I encountered an unexpected error while attempting to search."
                    logger.error(f"[SEARCH] Execution failed: {e}")

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

            elif intent in ["open_app", "application.launch"]:
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application should I open, Sir?"
                else:
                    from core.apps.application_discovery import app_discovery
                    best_app, candidates = app_discovery.find_application(target)
                    if candidates and not best_app:
                        cand_names = [c.display_name for c in candidates[:4]]
                        cand_str = ", ".join(cand_names)
                        success = False
                        outcome = CommandOutcome.MISSING_ARGUMENT
                        message = f"Multiple applications matched '{target}': {cand_str}. Which one would you like to open, Sir?"
                    else:
                        success = app_control.open_app(target)
                        if success:
                            outcome = CommandOutcome.SUCCESS
                            disp = best_app.display_name if best_app else target.title()
                            message = f"{disp} is open, Sir."
                        else:
                            outcome = CommandOutcome.UNSUPPORTED_CAPABILITY
                            message = "That application isn't installed, Sir."

            elif intent == "command_management":
                from core.custom_commands.command_manager import command_manager
                cmd_res = command_manager.handle_management_command(target or intent_node.get("query", ""), confirm=confirm)
                success = bool(cmd_res.get("success", False))
                message = cmd_res.get("message", "")
                if cmd_res.get("pending_confirmation"):
                    return {
                        "success": False,
                        "outcome": CommandOutcome.PERMISSION_DENIED.value,
                        "message": message,
                        "intent": intent,
                        "action": action,
                        "target": target,
                        "spoken": True,
                        "pending_confirmation": True
                    }
                raw_out = cmd_res.get("outcome")
                if raw_out:
                    try:
                        outcome = CommandOutcome(raw_out)
                    except ValueError:
                        outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED
                else:
                    outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

            elif intent == "custom_command":
                from core.custom_commands.workflow_engine import workflow_engine
                from core.custom_commands.command_manager import command_manager
                wf = intent_node.get("workflow", [])
                wf_res = workflow_engine.execute_workflow(wf, confirm=confirm, executor=self)
                success = bool(wf_res.get("success", False))
                message = wf_res.get("message", "")
                if wf_res.get("pending_confirmation"):
                    return {
                        "success": False,
                        "outcome": CommandOutcome.PERMISSION_DENIED.value,
                        "message": message,
                        "intent": intent,
                        "action": action,
                        "target": target,
                        "spoken": True,
                        "pending_confirmation": True
                    }
                if not success:
                    first_fail = next((s for s in wf_res.get("steps", []) if s.get("status") == "FAILED"), None)
                    command_manager.last_failed_command_info = {
                        "command_name": intent_node.get("command_name", "custom_command"),
                        "step_index": (first_fail.get("step_index", 0) + 1) if first_fail else 1,
                        "reason": first_fail.get("message") if first_fail else message
                    }
                    outcome = CommandOutcome.EXECUTION_FAILED
                else:
                    outcome = CommandOutcome.SUCCESS

            elif intent == "close_app":
                if not target:
                    success = False
                    outcome = CommandOutcome.MISSING_ARGUMENT
                    message = "Which application should I close, Sir?"
                else:
                    success = app_control.close_app(target)
                    if success:
                        outcome = CommandOutcome.SUCCESS
                        message = f"{target.title()} is closed, Sir."
                    else:
                        outcome = CommandOutcome.EXECUTION_FAILED
                        message = f"I couldn't close {target}, Sir."

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
                elif action == "create_folder":
                    folder_path = self.filesystem_mgr.resolve_path(target or "New Folder")
                    try:
                        os.makedirs(folder_path, exist_ok=True)
                        success = folder_path.exists() and folder_path.is_dir()
                        message = f"Created folder {folder_path.name}." if success else "Failed to create folder."
                    except Exception as fe:
                        success = False
                        message = f"Error creating folder: {fe}"
                elif action in ["save_file", "write_file"]:
                    file_content = intent_node.get("content") or intent_node.get("query") or ""
                    res = self.content_gen.create_and_save_file(target, file_content)
                    success = res.get("success", False)
                    message = res.get("message", "")
                    if success:
                        self.last_created_file = res.get("path")
                else:
                    success = False
                    message = f"Unknown filesystem action: {action}"

            elif intent == "browser_control":
                success, message = self._handle_browser_control(action, target, intent_node)

            elif intent == "youtube_control":
                res = self.browser_mgr.youtube_control(action, target)
                success = res.get("success", False)
                message = res.get("message", "YouTube playback updated.")

            elif intent == "content_generation":
                ctype = intent_node.get("content_type", "general")
                topic = intent_node.get("target") or intent_node.get("query", "General")
                res = self.content_gen.draft_content(topic, content_type=ctype)
                success = res.get("success", True)
                message = res.get("content", "")

            elif intent in ["local_search", "search_code"]:
                cwd = self.project_registry.get_current_project()["path"]
                if action == "search_code":
                    res = self.filesystem_mgr.search_content(target or intent_node.get("query", ""), base_dir=cwd)
                    success = res.get("success", False)
                    if success and res.get("results"):
                        self.last_search_results = res["results"]
                        names = [Path(r).name for r in res["results"][:3]]
                        message = f"Found {res['count']} code references: {', '.join(names)}."
                    else:
                        message = f"No references found for '{target}' in {Path(cwd).name}."
                else:
                    folder = intent_node.get("folder")
                    search_dir = cwd
                    if folder == "downloads":
                        search_dir = str(Path.home() / "Downloads")
                    ext = intent_node.get("extension")
                    res = self.filesystem_mgr.search_files(target or intent_node.get("query", ""), base_dir=search_dir, extension=ext)
                    success = res.get("success", False)
                    if success and res.get("matches"):
                        self.last_search_results = res["matches"]
                        names = [Path(m).name for m in res["matches"][:3]]
                        message = f"Found matches: {', '.join(names)}."
                    else:
                        message = f"No files found matching '{target}'."

            elif intent == "developer_workflow":
                cwd = self.project_registry.get_current_project()["path"]
                if action == "run_tests":
                    cmd = ".venv\\Scripts\\python -m unittest discover tests" if os.name == "nt" else "python3 -m unittest discover tests"
                    res = self.terminal_mgr.execute(cmd, cwd=cwd)
                    out = (res.get("stdout") or "") + (res.get("stderr") or "")
                    if "Ran " in out or "OK" in out or "FAILED" in out:
                        success = "FAILED" not in out
                        lines = [line for line in out.splitlines() if "Ran " in line or "OK" in line or "FAILED" in line]
                        summary = " ".join(lines[-2:]) if lines else "Tests completed."
                        message = f"Test execution completed: {summary}"
                    else:
                        success = res.get("success", False)
                        message = f"Tests completed with output: {out[:120]}"
                else:
                    success = False
                    message = f"Unknown developer workflow action: {action}"

            elif intent == "follow_up":
                if action == "open_last_created_file":
                    if self.last_created_file:
                        res = self.filesystem_mgr.open_file(self.last_created_file)
                        success = res.get("success", False)
                        message = res.get("message", f"Opened {Path(self.last_created_file).name}.")
                    else:
                        success = False
                        message = "No recently created file found to open."
                elif action == "open_result_index":
                    idx = int(target) - 1 if str(target).isdigit() else 0
                    if self.last_search_results and 0 <= idx < len(self.last_search_results):
                        item = self.last_search_results[idx]
                        if item.startswith("http"):
                            success, message = web_control.open_website(item)
                        else:
                            res = self.filesystem_mgr.open_file(item)
                            success = res.get("success", False)
                            message = res.get("message", f"Opened {Path(item).name}.")
                    else:
                        success = False
                        message = f"Result number {target} is not available."

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
                from core.tool_registry import tool_registry
                message = tool_registry.get_capabilities_summary()

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

            elif intent == "explain_tool_execution":
                from core.observability import tool_explainer
                exp_res = tool_explainer.explain_recent_executions()
                success = True
                message = exp_res["text"]

            elif intent == "memory_control":
                from core.profile_manager import profile_manager
                if action == "save":
                    mem_text = target or intent_node.get("query", "")
                    success = profile_manager.add_memory(mem_text)
                    message = f"Saved to memory: '{mem_text}'." if success else "Failed to save memory."
                elif action == "recall":
                    topic_text = target or intent_node.get("query", "")
                    mems = profile_manager.query_memories(topic_text)
                    success = True
                    if mems:
                        message = "Here is what I remember:\n" + "\n".join(f"- {m}" for m in mems[:5])
                    else:
                        message = f"I don't have any saved notes about '{topic_text}'."
                elif action == "forget":
                    topic_text = target or intent_node.get("query", "")
                    success = profile_manager.forget_memory(topic_text)
                    message = f"Removed memory matching '{topic_text}'." if success else f"No memory found matching '{topic_text}'."
                else:
                    success = False
                    message = f"Unknown memory action: {action}"

            elif intent == "privacy_control":
                from core.security.privacy_guard import privacy_guard
                if action == "set_mode":
                    mode_val = (target or "GUARDED").upper()
                    success = privacy_guard.set_mode(mode_val)
                    mode_str = privacy_guard.get_mode()
                    message = f"Privacy mode updated to {mode_str}." if success else f"Invalid privacy mode '{target}'. Choose STRICT, GUARDED, or RELAXED."
                else:
                    mode_str = privacy_guard.get_mode()
                    success = True
                    if mode_str == "STRICT":
                        message = "Active privacy mode is STRICT: 100% local-first, zero cloud calls permitted."
                    elif mode_str == "GUARDED":
                        message = "Active privacy mode is GUARDED: Cloud permitted with automatic secret redaction and audit logging."
                    else:
                        message = "Active privacy mode is RELAXED: Direct cloud access without redaction (development mode)."

            elif intent == "unsupported_capability":
                success = False
                outcome = CommandOutcome.UNSUPPORTED_CAPABILITY
                message = "That capability isn't available yet, Sir."

            elif intent == "invalid_command":
                success = False
                outcome = CommandOutcome.INVALID_COMMAND
                message = "I couldn't complete that request, Sir. Try another command."

            else:
                success = False
                outcome = CommandOutcome.INVALID_COMMAND
                message = "I couldn't complete that request, Sir. Try another command."

        except Exception as e:
            logger.error(f"Execution failed with error: {e}", exc_info=True)
            success = False
            outcome = CommandOutcome.EXECUTION_FAILED
            message = "That action failed, Sir. Please try again."

        if outcome is None:
            outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

        result = {
            "success": success,
            "outcome": outcome.value if isinstance(outcome, CommandOutcome) else outcome,
            "message": message,
            "intent": intent,
            "action": action,
            "target": target,
            "spoken": True,
            "pending_confirmation": False
        }

        # 4. Record Action in History and Observability Tracking
        self._record_history(intent_node, result)
        try:
            dur_ms = (time.time() - t0) * 1000 if 't0' in locals() else 0.0
            from core.smart_memory import smart_memory
            from core.observability import tool_explainer
            smart_memory.record_tool_execution(intent, success, dur_ms, error=(message if not success else None))
            rationale = self._determine_tool_rationale(intent, intent_node)
            tool_explainer.record_decision(
                query=intent_node.get("raw_text") or intent_node.get("query") or intent,
                intent=intent,
                tool_name=intent,
                rationale=rationale,
                args={"target": target, "action": action},
                duration_ms=dur_ms,
                success=success,
                verification_evidence=f"Success={success}, OutputLength={len(message)}"
            )
        except Exception as oe:
            logger.debug(f"Observability record failed: {oe}")

        return result

    def _determine_tool_rationale(self, intent: str, node: dict) -> str:
        if intent == "web_search":
            prov = node.get("provider", "google")
            return f"Web search requested for provider '{prov}'."
        elif intent == "open_website":
            return f"Direct website navigation requested for destination '{node.get('target')}'."
        elif intent == "open_app":
            return f"Local application launch requested for '{node.get('target')}'."
        elif intent == "browser_control":
            return f"Browser tab or window control requested ({node.get('action')})."
        elif intent == "youtube_control":
            return f"YouTube video media playback control invoked ({node.get('action')})."
        elif intent == "content_generation":
            return f"Writing/drafting engine invoked for content type '{node.get('content_type', 'general')}'."
        elif intent == "filesystem_control":
            return f"Local filesystem operation invoked ({node.get('action')})."
        elif intent == "developer_workflow":
            return f"Developer project workflow invoked ({node.get('action')})."
        elif intent == "explain_tool_execution":
            return "User requested transparency report of recent tool calls."
        elif intent == "memory_control":
            return f"User profile memory operation invoked ({node.get('action')})."
        elif intent == "privacy_control":
            return f"Privacy policy inspection or update invoked ({node.get('action')})."
        elif intent == "system_control":
            return f"Deterministic OS system control invoked ({node.get('action')})."
        return f"Deterministic execution for intent '{intent}'."

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

    def _handle_browser_control(self, action: str, target: str, intent_node: dict) -> (bool, str):
        if action == "close_tab":
            res = self.browser_mgr.close_tab()
            return res.get("success", False), res.get("message", "Closed active tab.")
        elif action == "new_tab":
            res = self.browser_mgr.new_tab(url=target)
            return res.get("success", False), res.get("message", "Opened new tab.")
        elif action == "reopen_tab":
            res = self.browser_mgr.reopen_closed_tab()
            return res.get("success", False), res.get("message", "Reopened last closed tab.")
        elif action == "next_tab":
            res = self.browser_mgr.next_tab()
            return res.get("success", False), res.get("message", "Switched to next tab.")
        elif action in ["prev_tab", "previous_tab"]:
            res = self.browser_mgr.prev_tab()
            return res.get("success", False), res.get("message", "Switched to previous tab.")
        elif action == "reload_page":
            res = self.browser_mgr.reload_page()
            return res.get("success", False), res.get("message", "Page reloaded.")
        elif action == "go_back":
            res = self.browser_mgr.go_back()
            return res.get("success", False), res.get("message", "Navigated back.")
        elif action == "go_forward":
            res = self.browser_mgr.go_forward()
            return res.get("success", False), res.get("message", "Navigated forward.")
        elif action == "toggle_fullscreen":
            res = self.browser_mgr.toggle_fullscreen()
            return res.get("success", False), res.get("message", "Toggled fullscreen.")
        elif action == "open_downloads":
            res = self.browser_mgr.open_downloads()
            return res.get("success", False), res.get("message", "Opened browser downloads.")
        elif action == "open_history":
            res = self.browser_mgr.open_history()
            return res.get("success", False), res.get("message", "Opened browser history.")
        elif action == "list_tabs":
            res = self.browser_mgr.list_tabs()
            return res.get("success", False), res.get("message", "Listed open tabs.")
        elif action == "open_multiple":
            urls = intent_node.get("urls") or ([target] if target else [])
            res = self.browser_mgr.open_multiple_urls(urls)
            return res.get("success", False), res.get("message", "Opened websites.")
        else:
            return False, f"Unknown browser control action: {action}"

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
