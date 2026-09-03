# System Information Telemetry

## Overview
The System Information Provider (`core/os/system_info.py`) answers hardware, OS, network, and resource queries 100% locally with zero cloud API dependencies.

---

## Supported Natural Queries & Telemetry Responses

| User Query | Intent / Action | Telemetry Source | Sample Spoken Response |
|---|---|---|---|
| *"What CPU am I using?"* | `system_telemetry -> cpu_info` | `psutil` + `platform` | `"CPU: AMD64 Processor (8 cores) at 3400 MHz, currently at 12% usage."` |
| *"How much RAM do I have?"* | `system_telemetry -> ram_info` | `psutil.virtual_memory` | `"RAM: 8.2 GB used out of 16.0 GB (51% used, 7.8 GB available)."` |
| *"How much disk space is left?"* | `system_telemetry -> disk_info` | `psutil.disk_usage` | `"Disk Space (C:\): 120.4 GB free out of 512.0 GB (76% used)."` |
| *"What OS am I running?"* | `system_telemetry -> os_info` | `platform.system` | `"Operating System: Windows 10 (AMD64, Version 10.0.19045)."` |
| *"What is my local IP?"* | `system_telemetry -> ip_info` | `socket` | `"Local IP Address: 192.168.1.105"` |
| *"How long has system been running?"*| `system_telemetry -> uptime_info` | `psutil.boot_time` | `"System Uptime: 14 hours and 22 minutes."` |
