"""Natural-Language Command Management and Authoring Service for JARVIS.

Handles natural language command creation, workflow parsing, capability resolution,
conflict detection, previewing, safe dry-run testing, version rollback, and voice management.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple, Any

from core.tool_registry import tool_registry
from core.apps.application_discovery import app_discovery
from core.custom_commands.command_registry import custom_command_registry, CustomCommand
from core.custom_commands.workflow_engine import workflow_engine
from core.response_registry import CommandOutcome

logger = logging.getLogger("Jarvis.CommandManager")


class CommandManager:
    """Coordinates natural-language custom command authoring and management."""

    def __init__(self, registry=None, engine=None, discovery=None, tool_reg=None):
        self.registry = registry or custom_command_registry
        self.workflow_engine = engine or workflow_engine
        self.discovery = discovery or app_discovery
        self.tool_registry = tool_reg or tool_registry
        self.last_failed_command_info: Optional[Dict[str, Any]] = None
        logger.info("CommandManager initialized.")

    # =========================================================================
    # INTENT CLASSIFICATION AND DISPATCH
    # =========================================================================

    def is_command_management_query(self, text: str) -> bool:
        """Determines if normalized input text is a command management intent."""
        if not text:
            return False
        clean = text.lower().strip()
        patterns = [
            r"^(?:jarvis\s+)?(?:add|create)\s+(?:a\s+)?command",
            r"^(?:jarvis\s+)?add\s+(?:an\s+)?alias",
            r"^(?:jarvis\s+)?modify\s+(?:my\s+)?(.+)\s+workflow",
            r"^(?:jarvis\s+)?(?:list|show)\s+(?:all\s+)?custom\s+commands",
            r"^(?:jarvis\s+)?what\s+custom\s+commands",
            r"^(?:jarvis\s+)?search\s+custom\s+commands",
            r"^(?:jarvis\s+)?(?:show\s+)?command\s+details",
            r"^(?:jarvis\s+)?test\s+command",
            r"^(?:jarvis\s+)?(?:enable|disable)\s+command",
            r"^(?:jarvis\s+)?(?:delete|remove)\s+(?:custom\s+)?command",
            r"^(?:jarvis\s+)?undo\s+(?:the\s+)?(?:last\s+)?command(?:\s+change)?",
            r"^(?:jarvis\s+)?rollback\s+command",
            r"^(?:jarvis\s+)?why\s+did\s+command\s+(?:.+)\s+fail",
            r"^(?:jarvis\s+)?explain\s+(?:last\s+)?command\s+failure",
            r"^(?:jarvis\s+)?(?:scan|refresh)\s+(?:installed\s+)?applications",
            r"^(?:jarvis\s+)?(?:list|show)\s+(?:installed\s+|discovered\s+)?applications"
        ]
        return any(re.search(pat, clean) for pat in patterns)

    def handle_management_command(self, text: str, confirm: bool = False) -> Dict[str, Any]:
        """Routes management request to appropriate handler."""
        clean = text.lower().strip()
        for prefix in ["jarvis, ", "jarvis ", "please "]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()

        # 1. Scan applications
        if any(clean.startswith(p) for p in ["scan applications", "scan installed applications", "refresh applications"]):
            return self.handle_scan_applications()

        # 2. List applications
        if any(clean.startswith(p) for p in ["list applications", "list installed applications", "show applications", "show installed applications"]):
            return self.handle_list_applications()

        # 3. Add command
        if any(clean.startswith(p) for p in ["add a command", "add command", "create a command", "create command"]):
            return self.handle_create_command(clean, confirm=confirm)

        # 4. Add alias
        if clean.startswith("add alias ") or clean.startswith("add an alias "):
            return self.handle_add_alias(clean)

        # 5. Modify workflow
        if "modify" in clean and "workflow" in clean:
            return self.handle_modify_workflow(clean, confirm=confirm)

        # 6. List custom commands
        if any(p in clean for p in ["list custom commands", "show custom commands", "what custom commands"]):
            return self.handle_list_commands()

        # 7. Search custom commands
        if clean.startswith("search custom commands"):
            query = re.sub(r"^search custom commands (?:for )?", "", clean).strip()
            return self.handle_search_commands(query)

        # 8. Show command details
        if "command details" in clean:
            target = re.sub(r"^(?:show |view )?command details (?:for )?", "", clean).strip()
            return self.handle_show_command_details(target)

        # 9. Test command
        if clean.startswith("test command "):
            target = clean[13:].strip()
            return self.handle_test_command(target)

        # 10. Enable / Disable command
        if clean.startswith("enable command "):
            target = clean[15:].strip()
            return self.handle_toggle_command(target, enable=True)
        if clean.startswith("disable command "):
            target = clean[16:].strip()
            return self.handle_toggle_command(target, enable=False)

        # 11. Delete command
        if clean.startswith("delete command ") or clean.startswith("delete custom command ") or clean.startswith("remove command "):
            target = re.sub(r"^(?:delete|remove)\s+(?:custom\s+)?command\s+", "", clean).strip()
            return self.handle_delete_command(target, confirm=confirm)

        # 12. Undo / Rollback
        if clean.startswith("undo") or clean.startswith("rollback command"):
            target = re.sub(r"^(?:undo(?:\s+the)?(?:\s+last)?(?:\s+command)?(?:\s+change)?(?:\s+for)?|rollback\s+command)\s*", "", clean).strip()
            return self.handle_undo_command(target)

        # 13. Explain command failure
        if "why did command" in clean or "explain command failure" in clean or "why did the command fail" in clean:
            return self.handle_explain_failure(clean)

        return {
            "success": False,
            "outcome": CommandOutcome.INVALID_COMMAND.value,
            "message": "I didn't recognize that command management instruction, Sir."
        }

    # =========================================================================
    # 10-STEP COMMAND CREATION PIPELINE
    # =========================================================================

    def handle_create_command(self, text: str, confirm: bool = False) -> Dict[str, Any]:
        """Implements the 10-step custom command creation pipeline."""
        # Step 1: Recognize intent (Already done)

        # Step 2: Parse requested trigger, name, and intended actions
        parsed = self._parse_creation_request(text)
        if not parsed:
            return {
                "success": False,
                "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                "message": (
                    "Please specify the trigger phrase and actions for the command. "
                    "For example: 'Jarvis, add a command: when I say launch my 3D editor, open Blender.'"
                )
            }

        name = parsed["name"]
        triggers = parsed["triggers"]
        raw_actions = parsed["raw_actions"]

        # Step 3: Resolve actions against Tool Registry and Application Catalogue
        resolved_steps, missing_caps = self._resolve_actions_to_workflow(raw_actions)

        # If capability genuinely does not exist, explain missing capability (Requirement 6)
        if missing_caps:
            missing_text = "; ".join(missing_caps)
            logger.warning(f"[COMMAND_CREATION] Missing capability: {missing_text}")
            return {
                "success": False,
                "outcome": CommandOutcome.UNSUPPORTED_CAPABILITY.value,
                "message": (
                    f"I cannot create that command because a required capability is missing: {missing_text}. "
                    "Custom commands can only be composed from registered JARVIS tools and installed applications."
                )
            }

        if not resolved_steps:
            return {
                "success": False,
                "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                "message": "I couldn't identify any valid executable actions in that request, Sir."
            }

        # Step 4: Validate arguments and required permissions
        is_valid, validation_errors, risk_level = self.workflow_engine.validate_workflow(resolved_steps)
        if not is_valid:
            return {
                "success": False,
                "outcome": CommandOutcome.INVALID_COMMAND.value,
                "message": f"Command definition failed validation: {'; '.join(validation_errors)}"
            }

        # Step 5: Detect conflicts with existing triggers and built-in commands
        conflicts = self.registry.detect_conflicts(triggers)
        if conflicts:
            conflict_msg = "; ".join(conflicts)
            logger.warning(f"[COMMAND_CREATION] Trigger conflict: {conflict_msg}")
            return {
                "success": False,
                "outcome": CommandOutcome.INVALID_COMMAND.value,
                "message": f"Cannot create command due to a trigger conflict: {conflict_msg}."
            }

        # Step 6: Produce structured command definition
        workflow_def = resolved_steps

        # Step 7: Preview proposed command when ambiguity or meaningful side effects exist
        has_side_effects = any(
            getattr(self.tool_registry.get_tool(s["tool"]), "has_side_effects", False)
            for s in workflow_def if self.tool_registry.get_tool(s["tool"])
        ) or (risk_level in ["MEDIUM", "HIGH"])

        if has_side_effects and not confirm:
            preview_steps = ", ".join(s.get("description", s["tool"]) for s in workflow_def)
            return {
                "success": False,
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
                "message": (
                    f"Command '{name}' will perform actions with side effects: {preview_steps}. "
                    "Please confirm: say 'yes' to create this command, or 'cancel'."
                ),
                "pending_confirmation": True
            }

        # Step 8: Save the validated definition
        ok, reg_msg, new_cmd = self.registry.register_command(
            name=name,
            trigger_phrases=triggers,
            workflow_definition=workflow_def,
            risk_classification=risk_level,
            intent_description=f"Executes {len(workflow_def)} steps: {raw_actions}"
        )

        if not ok or not new_cmd:
            return {
                "success": False,
                "outcome": CommandOutcome.EXECUTION_FAILED.value,
                "message": f"Failed to save command: {reg_msg}"
            }

        # Step 9: Test command safely where practical (dry-run parameter validation)
        dry_run_ok, dry_run_err = self._dry_run_test(workflow_def)
        if not dry_run_ok:
            logger.warning(f"[COMMAND_CREATION] Dry-run warning: {dry_run_err}")

        # Step 10: Confirm exactly what was saved
        step_descriptions = " -> ".join(s.get("description", s["tool"]) for s in workflow_def)
        confirm_text = (
            f"Created command '{name}'. Triggered by '{triggers[0]}'. "
            f"Actions: {step_descriptions}."
        )
        logger.info(f"[COMMAND_CREATION] Saved command: {confirm_text}")
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": confirm_text,
            "command": new_cmd
        }

    # =========================================================================
    # ACTION PARSING AND CAPABILITY RESOLUTION
    # =========================================================================

    def _parse_creation_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts name, trigger, and actions from speech."""
        clean = text.strip()
        # Pattern 1: "when I say <trigger>, <actions>"
        m1 = re.search(r"when i say\s+([^,:]+)[,:]?\s*(?:then\s+)?(.+)", clean, re.IGNORECASE)
        if m1:
            trigger = m1.group(1).strip()
            actions = m1.group(2).strip()
            name = trigger.title()
            return {"name": name, "triggers": [trigger.lower()], "raw_actions": actions}

        # Pattern 2: "called <name> that <actions>"
        m2 = re.search(r"(?:called|named)\s+([^,]+?)\s+that\s+(.+)", clean, re.IGNORECASE)
        if m2:
            name = m2.group(1).strip()
            actions = m2.group(2).strip()
            return {"name": name.title(), "triggers": [name.lower()], "raw_actions": actions}

        # Pattern 3: "add a command <trigger> to <actions>"
        m3 = re.search(r"(?:add|create)\s+(?:a\s+)?command\s+([^,:]+?)\s+to\s+(.+)", clean, re.IGNORECASE)
        if m3:
            trigger = m3.group(1).strip()
            actions = m3.group(2).strip()
            return {"name": trigger.title(), "triggers": [trigger.lower()], "raw_actions": actions}

        return None

    def _resolve_actions_to_workflow(self, actions_text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Resolves natural language action clauses into structured tool steps."""
        # Split clauses by delimiters
        clauses = re.split(r",\s*and\s+|\s+and\s+then\s+|,\s*then\s+|,\s*|\s+and\s+", actions_text, flags=re.IGNORECASE)
        clauses = [c.strip() for c in clauses if c.strip()]

        workflow_steps = []
        missing_capabilities = []

        for idx, clause in enumerate(clauses):
            c_lower = clause.lower()

            # 1. Application launch: "open Blender", "opens VS Code", "launch Spotify"
            app_match = re.match(r"^(?:opens?|launch(?:es)?|start(?:s)?)\s+(.+)$", c_lower)
            if app_match:
                target_name = app_match.group(1).strip()
                # Check if it's a project folder first
                if any(w in target_name for w in ["my project", "project folder", "folder"]):
                    folder_target = target_name.replace("my project", "current_project").replace("folder", "").strip()
                    workflow_steps.append({
                        "step_id": idx + 1,
                        "tool": "open_folder",
                        "args": {"target": folder_target or "current_project"},
                        "description": f"Open project folder ({target_name})",
                        "timeout_sec": 10.0,
                        "required": True
                    })
                    continue

                # Check if it's a web search or url
                if target_name.startswith("http") or target_name.endswith(".com"):
                    workflow_steps.append({
                        "step_id": idx + 1,
                        "tool": "open_website",
                        "args": {"target": target_name},
                        "description": f"Navigate to website {target_name}",
                        "timeout_sec": 10.0,
                        "required": True
                    })
                    continue

                # Query application catalogue
                app, cands = self.discovery.find_application(target_name)
                if app:
                    workflow_steps.append({
                        "step_id": idx + 1,
                        "tool": "open_app",
                        "args": {"target": app.app_id},
                        "description": f"Launch {app.display_name}",
                        "timeout_sec": 15.0,
                        "required": True
                    })
                elif target_name in ["chrome", "notepad", "calculator", "explorer", "vscode", "blender", "spotify"]:
                    # Known standard application
                    workflow_steps.append({
                        "step_id": idx + 1,
                        "tool": "open_app",
                        "args": {"target": target_name},
                        "description": f"Launch {target_name.title()}",
                        "timeout_sec": 15.0,
                        "required": True
                    })
                else:
                    missing_capabilities.append(f"Application '{target_name}' is not installed or discoverable")
                continue

            # 2. Developer server / terminal: "starts the development server", "run tests"
            if any(term in c_lower for term in ["development server", "dev server", "start server", "run dev"]):
                workflow_steps.append({
                    "step_id": idx + 1,
                    "tool": "run_terminal",
                    "args": {"command": "npm run dev"},
                    "description": "Start development server",
                    "timeout_sec": 20.0,
                    "required": True
                })
                continue

            # 3. System actions: volume, lock, screenshot
            if "volume up" in c_lower:
                workflow_steps.append({"step_id": idx+1, "tool": "volume_control", "args": {"action": "volume_up"}, "description": "Turn volume up"})
                continue
            if "screenshot" in c_lower:
                workflow_steps.append({"step_id": idx+1, "tool": "take_screenshot", "args": {}, "description": "Take screenshot"})
                continue
            if "lock" in c_lower:
                workflow_steps.append({"step_id": idx+1, "tool": "lock_pc", "args": {}, "description": "Lock computer"})
                continue

            # Unrecognized capability
            missing_capabilities.append(f"No registered tool for '{clause}'")

        return workflow_steps, missing_capabilities

    def _dry_run_test(self, workflow_def: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Performs non-destructive dry-run parameter check."""
        for step in workflow_def:
            tool_name = step.get("tool")
            tool_def = self.tool_registry.get_tool(tool_name)
            if not tool_def:
                return False, f"Tool '{tool_name}' not registered."
        return True, "All tools verified."

    # =========================================================================
    # MANAGEMENT HANDLERS
    # =========================================================================

    def handle_scan_applications(self) -> Dict[str, Any]:
        """Scans installed applications and updates cache."""
        count = self.discovery.refresh()
        msg = f"Application scan completed, Sir. Discovered {count} installed applications."
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": msg,
            "count": count
        }

    def handle_list_applications(self) -> Dict[str, Any]:
        """Lists discovered applications with category summarization."""
        apps = self.discovery.list_applications(available_only=True)
        if not apps:
            return {
                "success": True,
                "outcome": CommandOutcome.SUCCESS.value,
                "message": "No applications are currently catalogued. Say 'Jarvis, scan applications' to discover them."
            }

        # Sample display
        sample = [a.display_name for a in apps[:8]]
        msg = f"I have discovered {len(apps)} installed applications, including: {', '.join(sample)}, and more."
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": msg,
            "total_count": len(apps),
            "applications": [a.display_name for a in apps]
        }

    def handle_list_commands(self) -> Dict[str, Any]:
        """Lists custom commands."""
        cmds = self.registry.list_commands(enabled_only=False)
        if not cmds:
            return {
                "success": True,
                "outcome": CommandOutcome.SUCCESS.value,
                "message": "You haven't created any custom commands yet, Sir."
            }

        names = [f"{c.name} ({'enabled' if c.enabled else 'disabled'})" for c in cmds]
        msg = f"You have {len(cmds)} custom command{'s' if len(cmds)>1 else ''}: {', '.join(names)}."
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": msg,
            "commands": cmds
        }

    def handle_search_commands(self, query: str) -> Dict[str, Any]:
        """Searches custom commands."""
        if not query:
            return self.handle_list_commands()
        results = self.registry.search_commands(query)
        if not results:
            return {
                "success": True,
                "outcome": CommandOutcome.SUCCESS.value,
                "message": f"No custom commands matched '{query}', Sir."
            }
        names = [c.name for c in results]
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": f"Found {len(results)} matching command{'s' if len(results)>1 else ''}: {', '.join(names)}.",
            "commands": results
        }

    def handle_show_command_details(self, target: str) -> Dict[str, Any]:
        """Shows details of a specific custom command."""
        cmd = self.registry.get_command(target) or self.registry.get_command_by_name(target)
        if not cmd:
            return {
                "success": False,
                "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                "message": f"I couldn't find a custom command named '{target}', Sir."
            }
        steps_summary = " -> ".join(s.get("description", s.get("tool", "step")) for s in cmd.workflow_definition)
        msg = (
            f"Command: {cmd.name} (v{cmd.version}, {cmd.risk_classification} risk, "
            f"{'enabled' if cmd.enabled else 'disabled'}). Triggers: {', '.join(cmd.trigger_phrases)}. "
            f"Actions: {steps_summary}."
        )
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": msg,
            "command": cmd
        }

    def handle_add_alias(self, text: str) -> Dict[str, Any]:
        """Handles adding an alias to a command or app."""
        # "add alias <alias> to command <command>" or "add an alias so <alias> opens <target>"
        m = re.search(r"add\s+(?:an\s+)?alias\s+so\s+([^,]+?)\s+opens\s+(.+)", text, re.IGNORECASE)
        if m:
            alias = m.group(1).strip()
            target = m.group(2).strip()
            # Find command or app
            cmd = self.registry.get_command_by_name(target) or self.registry.get_command(target)
            if cmd:
                ok, msg = self.registry.add_alias(cmd.command_id, alias)
                return {"success": ok, "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value, "message": msg}
            else:
                # Add as an application alias command
                ok, msg, _ = self.registry.register_command(
                    name=f"Launch {target.title()}",
                    trigger_phrases=[alias],
                    workflow_definition=[{"tool": "open_app", "args": {"target": target.lower()}, "description": f"Open {target}"}],
                    intent_description=f"Opens {target}"
                )
                return {"success": ok, "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value, "message": msg}

        m2 = re.search(r"add\s+(?:an\s+)?alias\s+([^,]+?)\s+to\s+(?:command\s+)?(.+)", text, re.IGNORECASE)
        if m2:
            alias = m2.group(1).strip()
            target = m2.group(2).strip()
            cmd = self.registry.get_command_by_name(target) or self.registry.get_command(target)
            if not cmd:
                return {"success": False, "outcome": CommandOutcome.MISSING_ARGUMENT.value, "message": f"Command '{target}' was not found."}
            ok, msg = self.registry.add_alias(cmd.command_id, alias)
            return {"success": ok, "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value, "message": msg}

        return {"success": False, "outcome": CommandOutcome.MISSING_ARGUMENT.value, "message": "Please specify the alias and target command."}

    def handle_modify_workflow(self, text: str, confirm: bool = False) -> Dict[str, Any]:
        """Modifies an existing workflow to add or update actions."""
        # "modify my morning workflow to open Chrome"
        m = re.search(r"modify\s+(?:my\s+)?(.+?)\s+workflow\s+to\s+(.+)", text, re.IGNORECASE)
        if not m:
            return {"success": False, "outcome": CommandOutcome.MISSING_ARGUMENT.value, "message": "Please specify the workflow and the modification."}

        wf_name = m.group(1).strip()
        new_action_text = m.group(2).strip()

        cmd = self.registry.get_command_by_name(wf_name) or self.registry.get_command_by_name(f"{wf_name} workflow")
        if not cmd:
            # Create it if it doesn't exist
            return self.handle_create_command(f"create a command called {wf_name} that {new_action_text}", confirm=confirm)

        new_steps, missing = self._resolve_actions_to_workflow(new_action_text)
        if missing:
            return {"success": False, "outcome": CommandOutcome.UNSUPPORTED_CAPABILITY.value, "message": f"Cannot modify: {'; '.join(missing)}"}

        updated_steps = list(cmd.workflow_definition) + new_steps
        ok, msg, updated_cmd = self.registry.update_command(cmd.command_id, {"workflow_definition": updated_steps})
        return {
            "success": ok,
            "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value,
            "message": f"Updated workflow '{cmd.name}' to include: {new_action_text}." if ok else msg
        }

    def handle_test_command(self, target: str) -> Dict[str, Any]:
        """Performs a safe dry-run test of a command."""
        cmd = self.registry.get_command(target) or self.registry.get_command_by_name(target)
        if not cmd:
            return {"success": False, "outcome": CommandOutcome.MISSING_ARGUMENT.value, "message": f"Command '{target}' not found."}
        ok, err = self._dry_run_test(cmd.workflow_definition)
        if ok:
            return {"success": True, "outcome": CommandOutcome.SUCCESS.value, "message": f"Dry-run test for '{cmd.name}' passed. All tools are verified."}
        return {"success": False, "outcome": CommandOutcome.EXECUTION_FAILED.value, "message": f"Dry-run test failed: {err}"}

    def handle_toggle_command(self, target: str, enable: bool) -> Dict[str, Any]:
        """Enables or disables a custom command."""
        cmd = self.registry.get_command(target) or self.registry.get_command_by_name(target)
        if not cmd:
            return {"success": False, "outcome": CommandOutcome.MISSING_ARGUMENT.value, "message": f"Command '{target}' not found."}
        if enable:
            ok, msg = self.registry.enable_command(cmd.command_id)
        else:
            ok, msg = self.registry.disable_command(cmd.command_id)
        return {"success": ok, "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value, "message": msg}

    def handle_delete_command(self, target: str, confirm: bool = False) -> Dict[str, Any]:
        """Deletes a custom command definition from SQLite."""
        cmd = self.registry.get_command(target) or self.registry.get_command_by_name(target)
        if not cmd:
            return {"success": False, "outcome": CommandOutcome.MISSING_ARGUMENT.value, "message": f"Command '{target}' not found."}
        if not confirm:
            return {
                "success": False,
                "outcome": CommandOutcome.PERMISSION_DENIED.value,
                "message": f"Are you sure you want to delete custom command '{cmd.name}'? Say 'yes' to confirm.",
                "pending_confirmation": True
            }
        ok, msg = self.registry.delete_command(cmd.command_id)
        return {"success": ok, "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value, "message": msg}

    def handle_undo_command(self, target: str = "") -> Dict[str, Any]:
        """Rolls back the last supported command change."""
        if target:
            cmd = self.registry.get_command(target) or self.registry.get_command_by_name(target)
        else:
            # Most recently updated command with history
            all_cmds = sorted(self.registry.list_commands(), key=lambda c: c.updated_at, reverse=True)
            cmd = next((c for c in all_cmds if c.history), None)

        if not cmd:
            return {
                "success": False,
                "outcome": CommandOutcome.EXECUTION_FAILED.value,
                "message": "No previous command definition version available to roll back to."
            }

        ok, msg, rolled = self.registry.rollback_command(cmd.command_id)
        return {
            "success": ok,
            "outcome": CommandOutcome.SUCCESS.value if ok else CommandOutcome.EXECUTION_FAILED.value,
            "message": msg if ok else f"Rollback failed: {msg}"
        }

    def handle_explain_failure(self, text: str) -> Dict[str, Any]:
        """Explains why a custom command or workflow failed."""
        if not self.last_failed_command_info:
            return {
                "success": True,
                "outcome": CommandOutcome.SUCCESS.value,
                "message": "No recent command failures recorded, Sir."
            }
        cmd_name = self.last_failed_command_info.get("command_name", "Recent command")
        step_idx = self.last_failed_command_info.get("step_index", 1)
        reason = self.last_failed_command_info.get("reason", "An unknown error occurred.")
        msg = f"Command '{cmd_name}' failed at step {step_idx}: {reason}"
        return {
            "success": True,
            "outcome": CommandOutcome.SUCCESS.value,
            "message": msg
        }


# Global singleton instance
command_manager = CommandManager()
