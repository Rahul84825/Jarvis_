# Process Manager Subsystem

## Overview
The Process Manager (`core/os/process_manager.py`) utilizes `psutil` for cross-platform process tracking, resource monitoring, process filtering, port inspection, and process termination.

---

## Core Capabilities

- `list_processes(filter_name: str = None) -> list`: Lists active processes with PID, process name, CPU %, and memory usage.
- `find_process(name_or_pid) -> list`: Finds process instances by name or PID.
- `terminate_process(target) -> dict`: Safely terminates processes matching a target name or PID.
- `get_top_cpu_processes(limit: int = 5) -> list`: Identifies high CPU-consuming processes.
- `get_port_process(port: int) -> Optional[dict]`: Inspects network connections to determine which process is listening on a target port (e.g., port 5000).
