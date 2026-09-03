'''
Utility helpers v2.0.0 — Process Engine
No Docker/Podman dependencies. Pure Python helpers.
'''

import os
import platform
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple


# ── Identity ───────────────────────────────────────────────────

def generate_id(prefix: str = "gbit") -> str:
    """Generate a unique ID"""
    short = uuid.uuid4().hex[:12]
    return f"{prefix}_{short}"


def sanitize_name(name: str) -> str:
    """Sanitize a service name for filesystem use"""
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_').lower()


# ── Port utilities ──────────────────────────────────────────────

def get_available_port(start_from: int = 3000, max_tries: int = 100) -> int:
    """Find an available port starting from start_from"""
    for port in range(start_from, start_from + max_tries):
        if not is_port_in_use(port):
            return port
    raise RuntimeError(f"Nenhuma porta disponivel no range {start_from}-{start_from + max_tries}")


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is in use"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except (OSError, socket.error):
        return False


def parse_port_mapping(mapping: str) -> Tuple[int, int]:
    """Parse port mapping like '8080:3000' -> (8080, 3000)"""
    parts = mapping.split(":")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    elif len(parts) == 1:
        port = int(parts[0])
        return port, port
    raise ValueError(f"Mapeamento de porta invalido: {mapping}")


# ── Format helpers ──────────────────────────────────────────────

def format_bytes(num_bytes: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_uptime(start_time: str) -> str:
    """Format uptime from ISO start time string"""
    try:
        start = datetime.fromisoformat(start_time)
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


# ── System info ────────────────────────────────────────────────

def get_system_info() -> Dict[str, Any]:
    """Get system information"""
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": socket.gethostname(),
        "os": platform.platform(),
    }


def get_system_stats() -> Dict[str, Any]:
    """Get system resource stats (CPU, memory)"""
    stats = {}

    # CPU count
    try:
        stats["cpu_count"] = os.cpu_count() or 0
    except Exception:
        stats["cpu_count"] = 0

    # Memory
    try:
        import psutil
        mem = psutil.virtual_memory()
        stats["memory_total"] = mem.total
        stats["memory_used"] = mem.used
        stats["memory_available"] = mem.available
        stats["memory_percent"] = mem.percent
        stats["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    except ImportError:
        # Fallback without psutil
        stats["memory_total"] = 0
        stats["memory_used"] = 0
        stats["memory_available"] = 0
        stats["memory_percent"] = 0
        stats["cpu_percent"] = 0

        # Try /proc/meminfo on Linux
        if sys.platform != "win32":
            try:
                with open("/proc/meminfo", "r") as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            key = parts[0].rstrip(':')
                            value = int(parts[1]) * 1024  # Convert kB to bytes
                            meminfo[key] = value
                    stats["memory_total"] = meminfo.get("MemTotal", 0)
                    stats["memory_available"] = meminfo.get("MemAvailable", 0)
                    stats["memory_used"] = stats["memory_total"] - stats["memory_available"]
                    if stats["memory_total"] > 0:
                        stats["memory_percent"] = round((stats["memory_used"] / stats["memory_total"]) * 100, 1)
            except Exception:
                pass

    # Load average (Unix only)
    if sys.platform != "win32":
        try:
            stats["load_avg"] = os.getloadavg()
        except (OSError, AttributeError):
            stats["load_avg"] = (0, 0, 0)
    else:
        stats["load_avg"] = (0, 0, 0)

    # Uptime
    try:
        if sys.platform != "win32":
            with open("/proc/uptime", "r") as f:
                uptime_secs = float(f.read().split()[0])
            stats["uptime"] = uptime_secs
        else:
            stats["uptime"] = 0
    except Exception:
        stats["uptime"] = 0

    return stats


# ── Process utilities ──────────────────────────────────────────

def is_process_alive(pid: int) -> bool:
    """Check if a process is alive by PID"""
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            # On Windows, use tasklist
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
        else:
            # Unix: signal 0 checks existence
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
            # Try SIGTERM first, then SIGKILL
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if is_process_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Also kill the process group
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                time.sleep(0.5)
            except (ProcessLookupError, OSError, PermissionError):
                pass
        return not is_process_alive(pid)
    except Exception:
        return False


def pause_process(pid: int) -> bool:
    """Pause a process via SIGSTOP (Unix only)"""
    if sys.platform == "win32":
        return False  # Windows has no SIGSTOP
    try:
        os.kill(pid, signal.SIGSTOP)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def unpause_process(pid: int) -> bool:
    """Unpause a process via SIGCONT (Unix only)"""
    if sys.platform == "win32":
        return False  # Windows has no SIGCONT
    try:
        os.kill(pid, signal.SIGCONT)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


# Need signal import at top
import signal


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
        # Fallback without psutil
        info = {"pid": pid, "name": "unknown", "status": "running"}
        try:
            if sys.platform != "win32":
                stat_path = f"/proc/{pid}/stat"
                with open(stat_path, "r") as f:
                    parts = f.read().split()
                    info["name"] = parts[1].strip("()")
                    info["status_code"] = parts[2]
        except (FileNotFoundError, PermissionError, IndexError):
            pass
        return info
    except Exception:
        return {"pid": pid, "name": "unknown", "status": "unknown"}


def check_binary_available(binary_name: str) -> bool:
    """Check if a binary is available in PATH"""
    if not binary_name:
        return False
    try:
        result = shutil.which(binary_name)
        return result is not None
    except Exception:
        return False


# shutil import needed
import shutil


def check_port_connectivity(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check if a TCP port is accepting connections"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (OSError, socket.error, socket.timeout):
        return False


# ── Subprocess wrapper ─────────────────────────────────────────

def run_command(cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None,
                capture: bool = True, timeout: int = 60) -> Dict[str, Any]:
    """Run a command via subprocess — simplified, no Docker/Podman workarounds"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env or os.environ.copy(),
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout if capture else "",
            "stderr": result.stderr if capture else "",
        }
    except FileNotFoundError:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": f"Comando nao encontrado: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": "Comando excedeu o tempo limite"}
    except Exception as e:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": str(e)}


# ── Platform info ──────────────────────────────────────────────

def get_platform_info() -> Dict[str, str]:
    """Get platform details"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "is_wsl": _is_wsl(),
        "is_mingw": _is_mingw(),
    }


def _is_wsl() -> bool:
    """Check if running in WSL"""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def _is_mingw() -> bool:
    """Check if running in MINGW/Git Bash"""
    return "MINGW" in os.environ.get("MSYSTEM", "") or "mingw" in platform.platform().lower()


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except (OSError, socket.error):
        return False
