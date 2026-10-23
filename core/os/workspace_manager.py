"""Personal Workspace Manager for JARVIS.
Handles declarative workspace profiles (Development, Gaming, Study, Research, Excel),
interactive optional action confirmation (e.g. Discord in gaming),
and bounded step execution with failure recovery.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from modules.system.executor import CommandExecutor
from memory.persistent_memory import persistent_memory

logger = logging.getLogger("Jarvis.WorkspaceManager")

class WorkspaceManager:
    """Loads, inspects, and coordinates execution of personal workspace environments."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or (Path(__file__).parent.parent.parent / "config" / "workspaces.json"))
        self.executor = CommandExecutor()
        self._workspaces: Dict[str, Any] = {}
        self._pending_executions: Dict[str, Dict[str, Any]] = {}
        self.load_workspaces()

    def load_workspaces(self) -> Dict[str, Any]:
        """Loads workspace definitions from JSON file."""
        if not self.config_path.exists():
            logger.warning(f"Workspaces config not found at {self.config_path}. Initializing empty.")
            self._workspaces = {}
            return self._workspaces

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._workspaces = json.load(f)
            logger.info(f"Loaded {len(self._workspaces)} personal workspaces from {self.config_path}.")
        except Exception as e:
            logger.error(f"Failed to parse workspaces.json: {e}")
            self._workspaces = {}
        return self._workspaces

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """Returns metadata for all available workspaces."""
        out = []
        for key, data in self._workspaces.items():
            out.append({
                "id": key,
                "name": data.get("name", key.title()),
                "description": data.get("description", ""),
                "aliases": data.get("aliases", []),
                "steps_count": len(data.get("steps", [])),
                "optional_actions": [opt.get("name", opt.get("id")) for opt in data.get("optional_actions", [])]
            })
        return out

    def get_workspace(self, identifier: str) -> Optional[tuple[str, Dict[str, Any]]]:
        """Looks up a workspace by canonical ID or alias."""
        clean = identifier.lower().strip()
        # Direct key lookup
        if clean in self._workspaces:
            return clean, self._workspaces[clean]

        # Alias lookup
        for key, data in self._workspaces.items():
            aliases = [a.lower() for a in data.get("aliases", [])]
            if clean in aliases or any(a in clean for a in aliases):
                return key, data

        return None

    def execute_workspace(
        self,
        identifier: str,
        confirmed_optional_ids: Optional[List[str]] = None,
        declined_optional_ids: Optional[List[str]] = None,
        always_optional_ids: Optional[List[str]] = None,
        never_optional_ids: Optional[List[str]] = None,
        completed_step_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Executes a personal workspace profile.
        If an optional action requires user confirmation and has no saved preference,
        prompts the user first before proceeding. Supports 'always' and 'never' to persist preferences.
        Tracks completed steps to ensure idempotent execution on resumption.
        """
        match = self.get_workspace(identifier)
        if not match:
            return {
                "success": False,
                "message": f"Workspace '{identifier}' could not be found. Registered workspaces: {', '.join(self._workspaces.keys())}."
            }

        ws_id, ws = match
        confirmed_ids = set(confirmed_optional_ids or [])
        declined_ids = set(declined_optional_ids or [])

        # Retrieve any previously saved execution state for this workspace
        pending_saved = self._pending_executions.pop(ws_id, {})
        done_ids = set(completed_step_ids or pending_saved.get("completed_step_ids", []))

        # Persist always preferences
        if always_optional_ids:
            for opt_id in always_optional_ids:
                persistent_memory.set_preference(f"workspace_{ws_id}_{opt_id}", "true")
                confirmed_ids.add(opt_id)

        # Persist never preferences
        if never_optional_ids:
            for opt_id in never_optional_ids:
                persistent_memory.set_preference(f"workspace_{ws_id}_{opt_id}", "false")
                declined_ids.add(opt_id)

        # 1. Check optional actions for pending interactive confirmation
        optional_actions = ws.get("optional_actions", [])
        for opt in optional_actions:
            opt_id = opt.get("id")
            # Check user saved preference in persistent memory first
            pref_raw = persistent_memory.get_preference(f"workspace_{ws_id}_{opt_id}")
            saved_pref = None
            if pref_raw is not None:
                if str(pref_raw).lower() in ["true", "1", "yes"]:
                    saved_pref = True
                elif str(pref_raw).lower() in ["false", "0", "no"]:
                    saved_pref = False

            if opt_id not in confirmed_ids and opt_id not in declined_ids:
                if saved_pref is True:
                    confirmed_ids.add(opt_id)
                elif saved_pref is False:
                    declined_ids.add(opt_id)
                elif opt.get("prompt"):
                    # Needs confirmation from user - save state for idempotent resume
                    prompt_msg = opt["prompt"]
                    self._pending_executions[ws_id] = {
                        "completed_step_ids": list(done_ids)
                    }
                    logger.info(f"[WORKSPACE_CONFIRMATION_REQUIRED] {prompt_msg}")
                    return {
                        "success": True,
                        "needs_confirmation": True,
                        "is_conversational_confirmation": True,
                        "workspace_id": ws_id,
                        "optional_id": opt_id,
                        "prompt": prompt_msg,
                        "message": prompt_msg
                    }

        # 2. Build ordered list of steps to execute
        steps_to_run = []
        for step in ws.get("steps", []):
            steps_to_run.append(step)

        for opt in optional_actions:
            if opt.get("id") in confirmed_ids:
                steps_to_run.append(opt)

        completed_steps = []
        failed_steps = []

        # 3. Execute steps sequentially with idempotency and failure tracking
        for step in steps_to_run:
            step_id = step.get("id") or step.get("name", "step")
            step_name = step.get("name", step.get("id", "step"))
            tool_name = step.get("tool")
            args = step.get("args", {})
            required = step.get("required", False)

            if step_id in done_ids:
                completed_steps.append(step_name)
                logger.info(f"[WORKSPACE_STEP_SKIPPED] Step '{step_name}' ({step_id}) already executed. Skipping.")
                continue

            intent_node = {
                "intent": tool_name,
                "action": args.get("action") or tool_name,
                "target": args.get("target") or args.get("url") or "",
                "entities": args
            }

            try:
                res = self.executor.execute(intent_node, confirm=True)
                if res.get("success", False):
                    completed_steps.append(step_name)
                    done_ids.add(step_id)
                    logger.info(f"[WORKSPACE_STEP_SUCCESS] Step '{step_name}' succeeded.")
                else:
                    msg = res.get("message", "Unknown error")
                    failed_steps.append((step_name, msg, required))
                    logger.warning(f"[WORKSPACE_STEP_FAILED] Step '{step_name}' failed: {msg}")
                    if required:
                        # Save completed state so retrying does not duplicate steps
                        self._pending_executions[ws_id] = {
                            "completed_step_ids": list(done_ids)
                        }
                        summary = f"Workspace '{ws.get('name')}' stopped: required step '{step_name}' failed ({msg}). Completed steps: {', '.join(completed_steps) or 'None'}."
                        return {
                            "success": False,
                            "workspace_id": ws_id,
                            "completed_steps": completed_steps,
                            "failed_step": step_name,
                            "message": summary
                        }
            except Exception as ex:
                failed_steps.append((step_name, str(ex), required))
                if required:
                    self._pending_executions[ws_id] = {
                        "completed_step_ids": list(done_ids)
                    }
                    summary = f"Workspace '{ws.get('name')}' halted: error in '{step_name}': {ex}."
                    return {
                        "success": False,
                        "workspace_id": ws_id,
                        "completed_steps": completed_steps,
                        "failed_step": step_name,
                        "message": summary
                    }

        # 4. Generate truthful completion summary
        ws_name = ws.get("name", ws_id.title())
        if failed_steps:
            non_req_fails = [f"{s} ({err})" for s, err, req in failed_steps if not req]
            summary = f"{ws_name} workspace prepared with {len(completed_steps)} steps ({', '.join(completed_steps)}). Optional items skipped: {', '.join(non_req_fails)}."
        else:
            summary = f"{ws_name} workspace is ready, Sir. All {len(completed_steps)} actions completed successfully."

        logger.info(f"[WORKSPACE_COMPLETED] {summary}")
        return {
            "success": True,
            "workspace_id": ws_id,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "message": summary
        }

workspace_manager = WorkspaceManager()
