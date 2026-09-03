import logging
import psutil
import subprocess
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.ProcessManager")

class ProcessManager:
    """Process Control Manager utilizing psutil for process monitoring, filtering,
    CPU/RAM metrics, port checking, and process termination across Windows and Linux.
    """

    def list_processes(self, filter_name: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists active running processes with PID, name, CPU %, and memory usage."""
        procs = []
        filter_clean = filter_name.lower().strip() if filter_name else ""
        try:
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    p_info = p.info
                    name = p_info.get('name') or ''
                    if filter_clean and filter_clean not in name.lower():
                        continue
                    procs.append({
                        "pid": p_info.get('pid'),
                        "name": name,
                        "cpu": p_info.get('cpu_percent') or 0.0,
                        "ram": round(p_info.get('memory_percent') or 0.0, 1)
                    })
                    if len(procs) >= limit:
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"[PROCESS_LIST_ERROR] Failed to list processes: {e}")

        logger.info(f"[PROCESS_LIST] Returned {len(procs)} process entries (filter='{filter_name}')")
        return procs

    def find_process(self, name_or_pid) -> List[Dict[str, Any]]:
        """Finds matching processes by PID or process name."""
        if str(name_or_pid).isdigit():
            target_pid = int(name_or_pid)
            try:
                p = psutil.Process(target_pid)
                return [{
                    "pid": p.pid,
                    "name": p.name(),
                    "status": p.status(),
                    "cpu": p.cpu_percent(interval=0.1),
                    "ram": round(p.memory_percent(), 1)
                }]
            except psutil.NoSuchProcess:
                return []
        return self.list_processes(filter_name=str(name_or_pid))

    def terminate_process(self, target) -> Dict[str, Any]:
        """Terminates matching process by PID or application name."""
        matches = self.find_process(target)
        if not matches:
            return {"success": False, "message": f"No running process found matching '{target}'."}

        terminated = []
        failed = []
        for p_info in matches:
            pid = p_info["pid"]
            name = p_info["name"]
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=2.0)
                terminated.append(f"{name} (PID {pid})")
            except Exception as e:
                logger.warning(f"Failed to terminate PID {pid}: {e}")
                failed.append(f"{name} (PID {pid})")

        if terminated:
            logger.info(f"[PROCESS_TERMINATED] Terminated: {', '.join(terminated)}")
            return {"success": True, "message": f"Terminated {', '.join(terminated)}."}
        return {"success": False, "message": f"Failed to terminate process matching '{target}'."}

    def get_top_cpu_processes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns the top processes consuming the most CPU."""
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                procs.append({
                    "pid": p.info['pid'],
                    "name": p.info['name'],
                    "cpu": p.info['cpu_percent'] or 0.0,
                    "ram": round(p.info['memory_percent'] or 0.0, 1)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x['cpu'], reverse=True)
        return procs[:limit]

    def get_port_process(self, port: int) -> Optional[Dict[str, Any]]:
        """Identifies which process is listening on a specific network port (e.g. port 5000)."""
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr and conn.laddr.port == port:
                    pid = conn.pid
                    if pid:
                        try:
                            proc = psutil.Process(pid)
                            return {
                                "port": port,
                                "pid": pid,
                                "name": proc.name(),
                                "status": conn.status
                            }
                        except psutil.NoSuchProcess:
                            return {"port": port, "pid": pid, "name": "Unknown", "status": conn.status}
        except Exception as e:
            logger.error(f"[PORT_CHECK_ERROR] Error checking port {port}: {e}")
        return None
