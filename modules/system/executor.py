import logging
from modules.system import app_control, window_control, system_control, screenshot, permissions
from modules.files import file_control

logger = logging.getLogger("Jarvis.Executor")

class CommandExecutor:
    """Central command execution engine.
    Validates, routes, and executes system commands, maintaining permission checks.
    """
    
    def __init__(self, history_tracker=None):
        self.history_tracker = history_tracker
        logger.info("Command Executor initialized.")

    def execute(self, intent_node: dict, confirm: bool = False) -> dict:
        """Executes a structured intent node command.
        
        Args:
            intent_node: Dictionary containing 'intent', 'action', 'target', or 'query'
            confirm: Boolean flag indicating if high-risk actions have been confirmed by user
        Returns:
            Dictionary representing structured execution results.
        """
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action")
        target = intent_node.get("target")
        
        logger.info(f"Executor received command: Intent='{intent}', Action='{action}', Target='{target}'")
        
        # 1. Validate Command Parameters for safety
        if not permissions.is_safe_command(intent, intent_node):
            result = {
                "success": False,
                "action": action or intent,
                "target": target,
                "message": "Action blocked: Command contains forbidden shell metacharacters."
            }
            self._record_history(intent_node, result)
            return result

        # 2. Risk and Permission Level Check
        risk_level = permissions.get_action_risk_level(intent, action)
        logger.info(f"Action safety classification: {risk_level}")
        
        if risk_level == permissions.RiskLevel.HIGH and not confirm:
            logger.info("High-risk action blocked. Awaiting user confirmation.")
            return {
                "success": False,
                "action": action or intent,
                "target": target,
                "pending_confirmation": True,
                "message": f"This action is high risk. Are you sure you want to proceed?"
            }

        # 3. Route Command to appropriate modules
        success = False
        message = ""
        
        try:
            if intent == "open_app":
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
                
            elif intent == "screenshot":
                if action == "open_folder":
                    success = screenshot.open_screenshot_folder()
                    message = "Opening screenshots folder." if success else "Failed to open screenshots folder."
                else:  # default is take screenshot
                    success, message = screenshot.take_screenshot()
                    
            elif intent == "system_control" or intent == "status_request":
                success, message = self._handle_system_control(action, target)
                
            else:
                message = f"Unknown or unexecutable intent: {intent}"
                
        except Exception as e:
            logger.error(f"Execution failed with error: {e}", exc_info=True)
            success = False
            message = f"Internal execution error: {e}"
            
        result = {
            "success": success,
            "action": action or intent,
            "target": target,
            "message": message
        }
        
        # 4. Record Action in History
        self._record_history(intent_node, result)
        return result

    def _handle_window_control(self, action: str, target: str) -> (bool, str):
        if action == "minimize":
            success = window_control.minimize_window(target)
            return success, f"Window minimized." if success else "Failed to minimize window."
        elif action == "maximize":
            success = window_control.maximize_window(target)
            return success, f"Window maximized." if success else "Failed to maximize window."
        elif action == "restore":
            success = window_control.restore_window(target)
            return success, f"Window restored." if success else "Failed to restore window."
        elif action in ["switch", "focus"]:
            if not target:
                return False, "No target window specified to switch to."
            success = window_control.switch_to_window(target)
            return success, f"Switched to {target}." if success else f"Failed to find window matching '{target}'."
        elif action == "close":
            success = window_control.close_window(target)
            return success, f"Closed window." if success else "Failed to close window."
        elif action in ["list", "list_open"]:
            titles = window_control.list_open_windows()
            if not titles:
                return True, "No open windows detected."
            # Limit returned list length for clean speech readouts
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
            return success, f"Opened file {target}." if success else f"Failed to open file."
        elif action == "search_file":
            if not target:
                return False, "No search term specified."
            matches = file_control.search_files(target)
            if not matches:
                return True, f"No matching files found for '{target}'."
            # Limit readouts to first 3 files
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
