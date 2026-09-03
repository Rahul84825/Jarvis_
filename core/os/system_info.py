import os
import sys
import time
import socket
import platform
import logging
import psutil
from typing import Dict, Any

logger = logging.getLogger("Jarvis.SystemInfoProvider")

class SystemInfoProvider:
    """100% Local System Telemetry Provider.
    Queries hardware metrics, memory, disk, network IPs, GPU details, and uptime locally with zero API dependency.
    """

    def get_cpu_info(self) -> Dict[str, Any]:
        proc_name = platform.processor() or "AMD64/x86_64 Processor"
        cores_logical = psutil.cpu_count(logical=True)
        cores_physical = psutil.cpu_count(logical=False) or cores_logical
        usage_pct = psutil.cpu_percent(interval=0.1)
        freq = psutil.cpu_freq()
        freq_mhz = f"{freq.current:.0f} MHz" if freq else "N/A"

        text = f"CPU: {proc_name} ({cores_physical} cores / {cores_logical} threads) at {freq_mhz}, currently at {usage_pct}% usage."
        return {"success": True, "text": text, "usage": usage_pct, "cores": cores_logical}

    def get_ram_info(self) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024 ** 3)
        avail_gb = mem.available / (1024 ** 3)
        used_gb = (mem.total - mem.available) / (1024 ** 3)
        pct = mem.percent

        text = f"RAM: {used_gb:.1f} GB used out of {total_gb:.1f} GB ({pct}% used, {avail_gb:.1f} GB available)."
        return {"success": True, "text": text, "total_gb": total_gb, "used_pct": pct}

    def get_disk_info(self, path: str = "/") -> Dict[str, Any]:
        target = "C:\\" if sys.platform == "win32" else "/"
        usage = psutil.disk_usage(target)
        total_gb = usage.total / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        pct = usage.percent

        text = f"Disk Space ({target}): {free_gb:.1f} GB free out of {total_gb:.1f} GB ({pct}% used)."
        return {"success": True, "text": text, "free_gb": free_gb, "total_gb": total_gb}

    def get_os_info(self) -> Dict[str, Any]:
        os_name = platform.system()
        os_rel = platform.release()
        os_ver = platform.version()
        arch = platform.machine()
        text = f"Operating System: {os_name} {os_rel} ({arch}, Version {os_ver})."
        return {"success": True, "text": text, "os": os_name, "release": os_rel}

    def get_network_ip(self) -> Dict[str, Any]:
        local_ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass
        text = f"Local IP Address: {local_ip}"
        return {"success": True, "text": text, "local_ip": local_ip}

    def get_uptime(self) -> Dict[str, Any]:
        boot_time = psutil.boot_time()
        uptime_sec = time.time() - boot_time
        hours = int(uptime_sec // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        text = f"System Uptime: {hours} hours and {minutes} minutes."
        return {"success": True, "text": text, "uptime_sec": uptime_sec}
