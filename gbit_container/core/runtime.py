'''
Runtime capabilities v2.0.0 — Process Engine
Platform/process capability checks, port availability, process lifecycle,
binary detection, system stats. Zero Docker/Podman references.
'''

import os
import platform
import signal
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional, List


# ── Platform detection ──────────────────────────────────────────

def get_platform_info() -> Dict[str, str]:
    """Get platform details"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "is_wsl": is_wsl(),
        "is_mingw": is_mingw(),
        "is_windows": platform.system() == "Windows",
        "is_macos": platform.system() == "Darwin",
        "is_linux": platform.system() == "Linux",
    }


def is_wsl() -> bool:
    """Check if running in Windows Subsystem for Linux"""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def is_mingw() -> bool:
    """Check if running in MINGW/Git Bash"""
    return "MINGW" in os.environ.get("MSYSTEM", "") or "mingw" in platform.platform().lower()


# ── System information ──────────────────────────────────────────

def get_system_info() -> Dict[str, Any]:
    """Get comprehensive system information"""
    info = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }

    # Engine info
    info["engine"] = "process_engine"
    info["engine_version"] = "2.0.0"
    info["engine_available"] = True  # Always available — no external dependencies

    return info


def get_system_stats() -> Dict[str, Any]:
    """Get system resource statistics"""
    stats = {"cpu_count": os.cpu_count() or 0}

    try:
        import psutil
        mem = psutil.virtual_memory()
        stats.update({
            "memory_total": mem.total,
            "memory_used": mem.used,
            "memory_available": mem.available,
            "memory_percent": mem.percent,
            "cpu_percent": psutil.cpu_percent(interval=0.5),
        })
    except ImportError:
        stats.update({
            "memory_total": 0, "memory_used": 0,
            "memory_available": 0, "memory_percent": 0, "cpu_percent": 0,
        })
        # Linux fallback
        if sys.platform != "win32":
            try:
                with open("/proc/meminfo", "r") as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            meminfo[parts[0].rstrip(':')] = int(parts[1]) * 1024
                    stats["memory_total"] = meminfo.get("MemTotal", 0)
                    stats["memory_available"] = meminfo.get("MemAvailable", 0)
                    stats["memory_used"] = stats["memory_total"] - stats["memory_available"]
                    if stats["memory_total"] > 0:
                        stats["memory_percent"] = round(stats["memory_used"] / stats["memory_total"] * 100, 1)
            except Exception:
                pass

    # Load average
    if sys.platform != "win32":
        try:
            stats["load_avg"] = list(os.getloadavg())
        except (OSError, AttributeError):
            stats["load_avg"] = [0, 0, 0]
    else:
        stats["load_avg"] = [0, 0, 0]

    return stats


# ── Port utilities ──────────────────────────────────────────────

def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except (OSError, socket.error):
        return False


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is in use"""
    return not is_port_available(port, host)


def check_port_connectivity(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check if a TCP port is accepting connections"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (OSError, socket.error, socket.timeout):
        return False


def get_available_port(start_from: int = 3000, max_tries: int = 100) -> int:
    """Find an available port"""
    for port in range(start_from, start_from + max_tries):
        if is_port_available(port):
            return port
    raise RuntimeError(f"Nenhuma porta disponivel no range {start_from}-{start_from + max_tries}")


# ── Process lifecycle ──────────────────────────────────────────

def is_process_alive(pid: int) -> bool:
    """Check if a process is alive by PID"""
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, OSError):
        return False
    except Exception:
        return False


def kill_process(pid: int, timeout: int = 10) -> bool:
    """Kill a process by PID"""
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=timeout)
        else:
            # SIGTERM first, then SIGKILL
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if is_process_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Kill process group too
            try:
                pgid = os.getpgid(pid)
                if pgid != os.getpid():  # Don't kill our own group
                    os.killpg(pgid, signal.SIGTERM)
                    time.sleep(0.5)
                    if is_process_alive(pid):
                        os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError, PermissionError):
                pass
        return not is_process_alive(pid)
    except Exception:
        return False


def pause_process(pid: int) -> bool:
    """Pause a process via SIGSTOP (Unix only)"""
    if sys.platform == "win32":
        return False
    try:
        os.kill(pid, signal.SIGSTOP)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def unpause_process(pid: int) -> bool:
    """Unpause a process via SIGCONT (Unix only)"""
    if sys.platform == "win32":
        return False
    try:
        os.kill(pid, signal.SIGCONT)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def get_process_info(pid: int) -> Optional[Dict[str, Any]]:
    """Get process info by PID"""
    if not pid or not is_process_alive(pid):
        return None
    try:
        import psutil
        proc = psutil.Process(pid)
        return {
            "pid": pid,
            "name": proc.name(),
            "cmdline": " ".join(proc.cmdline()),
            "status": proc.status(),
            "cpu_percent": proc.cpu_percent(),
            "memory_mb": proc.memory_info().rss / (1024 * 1024),
            "create_time": datetime.fromtimestamp(proc.create_time()).isoformat(),
            "num_threads": proc.num_threads(),
        }
    except ImportError:
        info = {"pid": pid, "name": "unknown", "status": "running"}
        try:
            if sys.platform != "win32":
                with open(f"/proc/{pid}/stat", "r") as f:
                    parts = f.read().split()
                    if len(parts) > 1:
                        info["name"] = parts[1].strip("()")
        except (FileNotFoundError, PermissionError, IndexError):
            pass
        return info
    except Exception:
        return {"pid": pid, "name": "unknown", "status": "unknown"}


# ── Binary detection ────────────────────────────────────────────

def check_binary_available(binary_name: str) -> bool:
    """Check if a binary is available in PATH"""
    if not binary_name:
        return False
    return shutil.which(binary_name) is not None


def find_binary(names: List[str]) -> Optional[str]:
    """Find first available binary from a list of names"""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


# ── Format helpers ──────────────────────────────────────────────

def format_bytes(num_bytes: float) -> str:
    """Format bytes to human-readable string"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_uptime(start_time_str: str) -> str:
    """Format uptime from ISO start time"""
    try:
        start = datetime.fromisoformat(start_time_str)
        delta = datetime.now() - start
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        return f"{minutes}m {seconds}s"
    except (ValueError, TypeError):
        return "N/A"


def format_duration(seconds: float) -> str:
    """Format seconds to human-readable duration"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"
