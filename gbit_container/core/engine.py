'''
ProcessEngine v2.0.0 — Native Process Orchestrator
Zero Docker/Podman dependencies. Services run as OS subprocesses.
'''

import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .runtime import (
    get_platform_info,
    get_system_info,
    get_system_stats,
    is_port_available,
    is_port_in_use,
    check_port_connectivity,
    is_process_alive,
    kill_process,
    pause_process,
    unpause_process,
    get_process_info,
    get_available_port,
    check_binary_available,
)
from ..utils.config import ConfigManager
from .. import __version__ as _GBIT_VERSION


class StackFilesMissingError(Exception):
    """Raised when required stack files are missing."""
    pass


class ProcessEngine:
    """Native process engine — manages services as OS subprocesses.

    Each service defined in gbit.yml runs as a subprocess tracked via .gbit/pids.json.
    Logs captured to .gbit/logs/<service>.log.
    Environment from .env.gbit + gbit.yml injected into subprocess.
    Port binding checks via Python socket.bind.
    Healthchecks via TCP port probes.
    """

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.config = ConfigManager(str(self.project_path))
        self.gbit_dir = self.project_path / ".gbit"
        self.pids_file = self.gbit_dir / "pids.json"
        self.logs_dir = self.gbit_dir / "logs"
        self.data_dir = self.gbit_dir / "data"
        self._processes: Dict[int, subprocess.Popen] = {}
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create .gbit directory structure"""
        self.gbit_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)

    # ── PID tracking ────────────────────────────────────────────

    def _load_pids(self) -> Dict[str, Any]:
        """Load pids.json"""
        if self.pids_file.exists():
            try:
                with open(self.pids_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_pids(self, data: Dict[str, Any]):
        """Save pids.json"""
        with open(self.pids_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _register_service(self, name: str, pid: int, cmd: str, port: Optional[int] = None, instance: int = 1):
        """Register a running service in pids.json"""
        pids = self._load_pids()
        key = f"{name}" if instance == 1 else f"{name}_{instance}"
        pids[key] = {
            "pid": pid,
            "cmd": cmd,
            "port": port,
            "instance": instance,
            "service": name,
            "status": "running",
            "start_time": datetime.now().isoformat(),
        }
        self._save_pids(pids)

    def _unregister_service(self, name: str, instance: int = 1):
        """Remove a service from pids.json"""
        pids = self._load_pids()
        key = f"{name}" if instance == 1 else f"{name}_{instance}"
        if key in pids:
            pids[key]["status"] = "stopped"
            pids[key]["pid"] = None
            self._save_pids(pids)

    def _update_service_status(self, name: str, status: str, instance: int = 1):
        """Update service status in pids.json"""
        pids = self._load_pids()
        key = f"{name}" if instance == 1 else f"{name}_{instance}"
        if key in pids:
            pids[key]["status"] = status
            self._save_pids(pids)

    # ── Environment ─────────────────────────────────────────────

    def _build_env(self, service_name: str, service_config: Dict[str, Any]) -> Dict[str, str]:
        """Build environment dict for a service subprocess"""
        env = os.environ.copy()

        # Load .env.gbit
        env_path = self.project_path / ".env.gbit"
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        env[key.strip()] = value.strip().strip('"').strip("'")

        # Service-level environment variables
        svc_env = service_config.get("environment", {})
        for key, value in svc_env.items():
            if isinstance(value, str):
                # Interpolate ${VAR} references
                import re
                pattern = r'\$\{([^}]+)\}'
                def _replace(m):
                    return env.get(m.group(1), os.environ.get(m.group(1), m.group(0)))
                env[key] = re.sub(pattern, _replace, value)
            else:
                env[key] = str(value)

        # Add service identity
        env["GBIT_SERVICE"] = service_name
        env["GBIT_PROJECT"] = self.config.get_project_name()

        return env

    # ── Command resolution ──────────────────────────────────────

    def _resolve_start_cmd(self, service_name: str, service_config: Dict[str, Any]) -> Optional[List[str]]:
        """Resolve the start command for a service.

        Priority: start_cmd > command > runtime-based default
        """
        # Explicit start_cmd
        start_cmd = service_config.get("start_cmd") or service_config.get("command")
        if start_cmd:
            if isinstance(start_cmd, str):
                return start_cmd.split()
            elif isinstance(start_cmd, list):
                return start_cmd
            return None

        # Runtime-based defaults
        runtime = service_config.get("runtime", "")
        build_dir = service_config.get("build", ".")

        runtime_cmds = {
            "node": ["npm", "start"],
            "python": ["python", "app.py"],
            "go": ["go", "run", "."],
            "rust": ["cargo", "run"],
            "java": ["mvn", "spring-boot:run"],
            "dotnet": ["dotnet", "run"],
            "php": ["php", "artisan", "serve"],
            "ruby": ["bundle", "exec", "rails", "server"],
        }

        if runtime in runtime_cmds:
            return runtime_cmds[runtime]

        # Fallback: check for common entry points
        build_path = self.project_path / build_dir if build_dir else self.project_path
        if (build_path / "package.json").exists():
            return ["npm", "start"]
        if (build_path / "app.py").exists():
            return ["python", "app.py"]
        if (build_path / "main.go").exists():
            return ["go", "run", "."]
        if (build_path / "Cargo.toml").exists():
            return ["cargo", "run"]
        if (build_path / "pom.xml").exists():
            return ["mvn", "spring-boot:run"]
        if (build_path / "Gemfile").exists():
            return ["bundle", "exec", "rails", "server"]

        return None

    def _resolve_build_cmd(self, service_name: str, service_config: Dict[str, Any]) -> Optional[List[str]]:
        """Resolve the build/install command for a service.

        This replaces the Docker 'build' step with dependency installation.
        """
        build_cmd = service_config.get("build_cmd")
        if build_cmd:
            if isinstance(build_cmd, str):
                return build_cmd.split()
            elif isinstance(build_cmd, list):
                return build_cmd
            return None

        runtime = service_config.get("runtime", "")
        build_dir = service_config.get("build", ".")

        runtime_build_cmds = {
            "node": ["npm", "install"],
            "python": ["pip", "install", "-r", "requirements.txt"],
            "go": ["go", "mod", "download"],
            "rust": ["cargo", "build"],
            "java": ["mvn", "compile"],
            "dotnet": ["dotnet", "build"],
            "php": ["composer", "install"],
            "ruby": ["bundle", "install"],
        }

        if runtime in runtime_build_cmds:
            return runtime_build_cmds[runtime]

        # Fallback: detect from project files
        build_path = self.project_path / build_dir if build_dir else self.project_path
        if (build_path / "package.json").exists():
            return ["npm", "install"]
        if (build_path / "requirements.txt").exists():
            return ["pip", "install", "-r", "requirements.txt"]
        if (build_path / "go.mod").exists():
            return ["go", "mod", "download"]
        if (build_path / "Cargo.toml").exists():
            return ["cargo", "build"]
        if (build_path / "pom.xml").exists():
            return ["mvn", "compile"]
        if (build_path / "composer.json").exists():
            return ["composer", "install"]
        if (build_path / "Gemfile").exists():
            return ["bundle", "install"]

        return None

    # ── Port resolution ──────────────────────────────────────────

    def _resolve_port(self, service_config: Dict[str, Any]) -> Optional[int]:
        """Resolve the primary host port for a service"""
        port = service_config.get("port")
        if port:
            return int(port)

        ports = service_config.get("ports", [])
        if ports:
            first_port = ports[0]
            if isinstance(first_port, str) and ":" in first_port:
                return int(first_port.split(":")[0])
            elif isinstance(first_port, int):
                return first_port
            elif isinstance(first_port, str):
                return int(first_port)

        return None

    # ── Core operations ─────────────────────────────────────────

    def initialize(self) -> Dict[str, Any]:
        """Initialize the engine (create dirs, validate config)"""
        self._ensure_dirs()
        errors = self.config.validate()
        if errors:
            return {"success": False, "errors": errors}
        return {"success": True, "errors": []}

    
    def up(self, services: Optional[List[str]] = None, detach: bool = True) -> Dict[str, Any]:
        """Start all or specified services as native subprocesses"""
        if not self.config.exists():
            return {"success": False, "error": f"gbit.yml nao encontrado em {self.project_path}"}

        try:
            self.config.load()
        except Exception as e:
            return {"success": False, "error": str(e)}

        all_services = self.config.get_services()
        target_services = services or list(all_services.keys())

        # Garante que dependências rodem primeiro (ex: 'database' antes de 'app' e 'portal')
        ordered_services = []
        for svc_name in target_services:
            svc_cfg = all_services.get(svc_name, {})
            deps = svc_cfg.get("depends_on", [])
            if isinstance(deps, dict):
                deps = list(deps.keys())
            for dep in deps:
                if dep in target_services and dep not in ordered_services:
                    ordered_services.append(dep)
            if svc_name not in ordered_services:
                ordered_services.append(svc_name)

        results = {"started": [], "failed": [], "skipped": []}

        for svc_name in ordered_services:
            if svc_name not in all_services:
                results["skipped"].append({"service": svc_name, "reason": "nao definido no gbit.yml"})
                continue

            # Verificação de processo já ativo
            pids = self._load_pids()
            if svc_name in pids and pids[svc_name].get("status") == "running":
                existing_pid = pids[svc_name].get("pid")
                if existing_pid and is_process_alive(existing_pid):
                    results["skipped"].append({"service": svc_name, "reason": "ja esta rodando"})
                    continue

            # Inicia o serviço
            start_result = self.start(svc_name)
            if start_result.get("success"):
                results["started"].append(svc_name)
            else:
                err_msg = start_result.get("error", "erro desconhecido ao iniciar o processo")
                results["failed"].append({"service": svc_name, "error": err_msg})

        # success é True se ao menos um iniciou ou já estava iniciado e nenhum falhou
        has_failures = len(results["failed"]) > 0
        return {"success": not has_failures, **results}



    def down(self, services: Optional[List[str]] = None) -> Dict[str, Any]:
        """Stop all or specified services"""
        pids = self._load_pids()

        if services:
            target_keys = []
            for svc in services:
                # Match service name and instances
                for key in pids:
                    if key == svc or key.startswith(f"{svc}_"):
                        target_keys.append(key)
        else:
            target_keys = list(pids.keys())

        results = {"stopped": [], "failed": []}

        for key in target_keys:
            entry = pids.get(key, {})
            pid = entry.get("pid")
            status = entry.get("status")

            if status == "running" and pid and is_process_alive(pid):
                if kill_process(pid):
                    self._update_service_status(entry.get("service", key), "stopped", entry.get("instance", 1))
                    results["stopped"].append(key)
                else:
                    results["failed"].append(key)
            elif status == "paused" and pid and is_process_alive(pid):
                unpause_process(pid)
                if kill_process(pid):
                    self._update_service_status(entry.get("service", key), "stopped", entry.get("instance", 1))
                    results["stopped"].append(key)
                else:
                    results["failed"].append(key)
            else:
                # Already stopped or dead — clean up
                self._update_service_status(entry.get("service", key), "stopped", entry.get("instance", 1))
                results["stopped"].append(key)

        # Wait briefly for cleanup
        time.sleep(0.5)

        # Refresh pids after stopping
        pids = self._load_pids()
        for key in results["stopped"]:
            if key in pids:
                pids[key]["status"] = "stopped"
                pids[key]["pid"] = None
        self._save_pids(pids)

        return {"success": len(results["failed"]) == 0, **results}

 
    def start(self, service_name: str) -> Dict[str, Any]:
        """Start a single service as a subprocess with strict path resolution."""
        if not self.config.exists():
            return {"success": False, "error": "gbit.yml nao encontrado"}

        try:
            self.config.load()
        except Exception:
            pass

        svc = self.config.get_service(service_name)
        if not svc:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado no gbit.yml"}

        cmd = self._resolve_start_cmd(service_name, svc)
        if not cmd:
            return {"success": False, "error": f"Servico '{service_name}': comando nao definido"}

        port = self._resolve_port(svc)

        # ── Resolução Inteligente da Pasta do Serviço (cwd) ──
        build_dir = svc.get("build") or svc.get("working_dir") or "."
        
        if build_dir == ".":
            # 1. Tenta a subpasta exata (ex: teste-db/database)
            dir_exact = self.project_path / service_name
            # 2. Tenta a subpasta com o prefixo 'gbit-' (ex: teste-db/gbit-database)
            dir_gbit = self.project_path / f"gbit-{service_name}"

            if dir_gbit.is_dir():
                cwd = str(dir_gbit)
            elif dir_exact.is_dir():
                cwd = str(dir_exact)
            else:
                cwd = str(self.project_path)
        else:
            cwd = str(self.project_path / build_dir)

        env = self._build_env(service_name, svc)
        svc_data_dir = self.data_dir / service_name
        svc_data_dir.mkdir(exist_ok=True)
        env["GBIT_DATA_DIR"] = str(svc_data_dir)

        log_file_path = self.logs_dir / f"{service_name}.log"

        try:
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if sys.platform == "win32":
                popen_kwargs = {
                    "args": cmd_str,
                    "cwd": cwd,
                    "env": env,
                    "shell": True,
                    "stdout": open(log_file_path, "a"),
                    "stderr": open(log_file_path, "a"),
                    "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
                }
            else:
                popen_kwargs = {
                    "args": cmd,
                    "cwd": cwd,
                    "env": env,
                    "stdout": open(log_file_path, "a"),
                    "stderr": open(log_file_path, "a"),
                    "start_new_session": True,
                }

            proc = subprocess.Popen(**popen_kwargs)
            self._processes[proc.pid] = proc

            self._register_service(service_name, proc.pid, cmd_str, port)

            time.sleep(0.6)

            if not is_process_alive(proc.pid):
                self._update_service_status(service_name, "stopped")
                return {
                    "success": False, 
                    "error": f"Processo '{service_name}' encerrou imediatamente em '{cwd}'. Verifique os logs em: {log_file_path}"
                }

            return {
                "success": True,
                "pid": proc.pid,
                "port": port,
                "cmd": cmd_str,
                "log": str(log_file_path),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

  


    def stop(self, service_name: str) -> Dict[str, Any]:
        """Stop a single service"""
        return self.down(services=[service_name])

    def restart(self, service_name: str) -> Dict[str, Any]:
        """Restart a service: stop then start"""
        stop_result = self.stop(service_name)
        time.sleep(0.5)
        start_result = self.start(service_name)
        return {
            "success": start_result.get("success", False),
            "stopped": stop_result.get("success", False),
            "started": start_result.get("success", False),
            "pid": start_result.get("pid"),
            "port": start_result.get("port"),
        }

    def pause(self, service_name: str) -> Dict[str, Any]:
        """Pause a service via SIGSTOP (Unix) or stop (Windows fallback)"""
        if sys.platform == "win32":
            # Windows has no SIGSTOP — stop as fallback
            return self.stop(service_name)

        pids = self._load_pids()
        if service_name not in pids:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

        entry = pids[service_name]
        pid = entry.get("pid")
        if not pid or not is_process_alive(pid):
            return {"success": False, "error": f"Servico '{service_name}' nao esta rodando"}

        if pause_process(pid):
            self._update_service_status(service_name, "paused")
            return {"success": True, "pid": pid}
        return {"success": False, "error": f"Falha ao pausar servico '{service_name}'"}

    def unpause(self, service_name: str) -> Dict[str, Any]:
        """Unpause a service via SIGCONT (Unix) or start (Windows fallback)"""
        if sys.platform == "win32":
            # Windows: start as fallback
            return self.start(service_name)

        pids = self._load_pids()
        if service_name not in pids:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

        entry = pids[service_name]
        pid = entry.get("pid")
        if not pid or not is_process_alive(pid):
            return self.start(service_name)

        if unpause_process(pid):
            self._update_service_status(service_name, "running")
            return {"success": True, "pid": pid}
        return {"success": False, "error": f"Falha ao despausar servico '{service_name}'"}

    # ── Build ────────────────────────────────────────────────────

    def build(self, services: Optional[List[str]] = None) -> Dict[str, Any]:
        """Install dependencies for services (replaces Docker image build)"""
        if not self.config.exists():
            return {"success": False, "error": "gbit.yml nao encontrado"}

        try:
            self.config.load()
        except Exception as e:
            return {"success": False, "error": str(e)}

        all_services = self.config.get_services()
        target_services = services or list(all_services.keys())

        results = {"built": [], "failed": [], "skipped": []}

        for svc_name in target_services:
            if svc_name not in all_services:
                results["skipped"].append({"service": svc_name, "reason": "nao definido"})
                continue

            svc = all_services[svc_name]
            build_cmd = self._resolve_build_cmd(svc_name, svc)

            if not build_cmd:
                results["skipped"].append({"service": svc_name, "reason": "nenhum build_cmd ou runtime detectado"})
                continue

            build_dir = svc.get("build", ".")
            if build_dir == ".":
                cwd = str(self.project_path)
            else:
                cwd = str(self.project_path / build_dir)

            env = self._build_env(svc_name, svc)

            try:
                log_file = self.logs_dir / f"{svc_name}_build.log"
                with open(log_file, "w") as log_f:
                    proc = subprocess.run(
                        build_cmd,
                        cwd=cwd,
                        env=env,
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                        timeout=300,
                    )

                if proc.returncode == 0:
                    results["built"].append({"service": svc_name, "cmd": " ".join(build_cmd)})
                else:
                    results["failed"].append({
                        "service": svc_name,
                        "error": f"build falhou com codigo {proc.returncode}",
                        "log": str(log_file),
                    })
            except FileNotFoundError:
                results["failed"].append({"service": svc_name, "error": f"Comando nao encontrado: {build_cmd[0]}"})
            except subprocess.TimeoutExpired:
                results["failed"].append({"service": svc_name, "error": "build excedeu o tempo limite (300s)"})
            except Exception as e:
                results["failed"].append({"service": svc_name, "error": str(e)})

        return {"success": len(results["failed"]) == 0, **results}

    # ── Logs ─────────────────────────────────────────────────────

    def logs(self, service_name: Optional[str] = None, lines: int = 100, follow: bool = False) -> Dict[str, Any]:
        """Get logs for a service or all services"""
        if service_name:
            log_path = self.logs_dir / f"{service_name}.log"
            if not log_path.exists():
                return {"success": False, "error": f"Nenhum log encontrado para '{service_name}'"}
            try:
                content = log_path.read_text(errors="replace")
                log_lines = content.splitlines()
                return {
                    "success": True,
                    "service": service_name,
                    "logs": log_lines[-lines:],
                    "total_lines": len(log_lines),
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            # All services
            all_logs = {}
            for log_file in self.logs_dir.glob("*.log"):
                svc_name = log_file.stem
                if svc_name.endswith("_build"):
                    continue
                try:
                    content = log_file.read_text(errors="replace")
                    log_lines = content.splitlines()
                    all_logs[svc_name] = {
                        "logs": log_lines[-lines:],
                        "total_lines": len(log_lines),
                    }
                except Exception:
                    pass
            return {"success": True, "services": all_logs}

    # ── Process list / status ─────────────────────────────────────

    def ps(self) -> List[Dict[str, Any]]:
        """List all defined services in gbit.yml along with their real-time execution status."""
        try:
            self.config.load()
        except Exception:
            pass

        all_services = self.config.get_services()
        pids = self._load_pids()
        result = []

        for svc_name, svc_cfg in all_services.items():
            # Tenta encontrar o registro de PID pelo nome do serviço ou pelas chaves cadastradas
            entry = pids.get(svc_name, {})
            pid = entry.get("pid")
            stored_status = entry.get("status", "stopped")

            # Valida se o processo com o PID registrado ainda está ativo no SO
            if pid:
                if is_process_alive(pid):
                    status = "running"
                else:
                    self._update_service_status(svc_name, "stopped", entry.get("instance", 1))
                    status = "stopped"
                    pid = None
            else:
                status = "stopped"

            # Resolve porta e comando diretamente da configuração do serviço
            port = self._resolve_port(svc_cfg) if hasattr(self, "_resolve_port") else svc_cfg.get("port")
            cmd = self._resolve_start_cmd(svc_name, svc_cfg) if hasattr(self, "_resolve_start_cmd") else svc_cfg.get("start_cmd", "")
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            # Verifica conectividade de porta se o processo estiver rodando
            healthy = False
            if port and status == "running":
                healthy = check_port_connectivity(port)

            result.append({
                "id": str(pid) if pid and status == "running" else "-",
                "name": svc_name,
                "service": svc_name,
                "instance": entry.get("instance", 1),
                "key": svc_name,
                "pid": pid if status == "running" else None,
                "status": status,
                "healthy": healthy,
                "port": port,
                "ports": [str(port)] if port else [],
                "command": cmd_str or "custom",
                "cmd": cmd_str,
                "start_time": entry.get("start_time", ""),
                "created": entry.get("start_time", "-"),
            })

        return result

    def status(self) -> Dict[str, Any]:
        """Calcula o status consolidado combinando gbit.yml e PIDs em tempo real."""
        containers = self.ps()

        running = sum(1 for c in containers if c["status"] == "running")
        stopped = sum(1 for c in containers if c["status"] == "stopped")
        total = len(containers)

        # Overall project status — o dashboard le este campo (`status`) para
        # o badge "Project Status". Sem ele, o front-end caia sempre no
        # texto padrao "Unknown" (vermelho), mesmo com servicos rodando.
        if total == 0:
            overall_status = "empty"
        elif running == total:
            overall_status = "running"
        elif running == 0:
            overall_status = "stopped"
        else:
            overall_status = "partial"

        project_name = self.config.get_project_name() if hasattr(self.config, "get_project_name") else self.project_path.name

        return {
            "engine": "process_engine",
            "version": _GBIT_VERSION,
            "available": True,
            "status": overall_status,
            "total_services": total,
            "total": total,
            "running": running,
            "stopped": stopped,
            "paused": 0,
            "services_running": f"{running} / {total}",
            "project": project_name,
            "project_path": str(self.project_path),
            "processes": containers,
        }



    def inspect(self, service_name: str) -> Dict[str, Any]:
        """Get detailed info about a service"""
        pids = self._load_pids()

        # Find service entries
        entries = {}
        for key, entry in pids.items():
            if key == service_name or entry.get("service") == service_name:
                entries[key] = entry

        if not entries:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

        # Get process info for running entries
        result = {"success": True, "service": service_name, "instances": []}
        for key, entry in entries.items():
            pid = entry.get("pid")
            proc_info = get_process_info(pid) if pid and is_process_alive(pid) else None

            instance_data = {
                **entry,
                "process": proc_info,
                "log_path": str(self.logs_dir / f"{service_name}.log"),
                "data_path": str(self.data_dir / service_name),
            }
            result["instances"].append(instance_data)

        return result

    def stats(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        """Get resource stats for services"""
        if service_name:
            pids = self._load_pids()
            if service_name not in pids:
                return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}
            pid = pids[service_name].get("pid")
            if not pid or not is_process_alive(pid):
                return {"success": False, "error": f"Servico '{service_name}' nao esta rodando"}
            proc_info = get_process_info(pid)
            return {"success": True, "service": service_name, **(proc_info or {})}
        else:
            # All services
            all_stats = []
            pids = self._load_pids()
            for key, entry in pids.items():
                pid = entry.get("pid")
                if pid and is_process_alive(pid) and entry.get("status") == "running":
                    proc_info = get_process_info(pid) or {}
                    all_stats.append({
                        "name": entry.get("service", key),
                        "pid": pid,
                        "port": entry.get("port"),
                        **proc_info,
                    })
            return {"success": True, "services": all_stats}

    # ── Exec / Shell ─────────────────────────────────────────────

    def exec(self, service_name: str, command: List[str]) -> Dict[str, Any]:
        """Execute a command in the context of a service's working directory"""
        try:
            self.config.load()
        except Exception:
            pass

        svc = self.config.get_service(service_name)
        if not svc:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

        build_dir = svc.get("build", ".")
        if build_dir == ".":
            cwd = str(self.project_path)
        else:
            cwd = str(self.project_path / build_dir)

        env = self._build_env(service_name, svc)

        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def shell(self, service_name: str) -> Dict[str, Any]:
        """Open an interactive shell in the service's working directory"""
        try:
            self.config.load()
        except Exception:
            pass

        svc = self.config.get_service(service_name)
        if not svc:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

        build_dir = svc.get("build", ".")
        if build_dir == ".":
            cwd = str(self.project_path)
        else:
            cwd = str(self.project_path / build_dir)

        env = self._build_env(service_name, svc)

        shell_cmd = os.environ.get("SHELL", "/bin/sh")
        if sys.platform == "win32":
            shell_cmd = os.environ.get("COMSPEC", "cmd.exe")

        try:
            subprocess.run([shell_cmd], cwd=cwd, env=env)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Healthcheck ──────────────────────────────────────────────

    def _wait_for_healthy(self, service_name: str, port: int, timeout: int = 30) -> bool:
        """Wait for a service to become healthy via TCP port probe"""
        start = time.time()
        while time.time() - start < timeout:
            if check_port_connectivity(port):
                return True
            time.sleep(0.5)
        return False

    def healthcheck(self, service_name: str) -> Dict[str, Any]:
        """Check health of a service via port probe"""
        pids = self._load_pids()
        if service_name not in pids:
            return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

        entry = pids[service_name]
        pid = entry.get("pid")
        port = entry.get("port")
        status = entry.get("status")

        alive = pid and is_process_alive(pid)
        port_ok = port and check_port_connectivity(port) if alive else False

        return {
            "success": True,
            "service": service_name,
            "process_alive": alive,
            "port_open": port_ok,
            "status": status,
            "healthy": alive and (port_ok if port else True),
        }

    # ── Scale ────────────────────────────────────────────────────

    def scale(self, service_name: str, count: int) -> Dict[str, Any]:
        """Scale a service to N instances"""
        pids = self._load_pids()

        # Count current instances
        current_instances = []
        for key, entry in pids.items():
            if entry.get("service") == service_name:
                current_instances.append((key, entry))

        current_count = len(current_instances)

        if count == current_count:
            return {"success": True, "message": f"Servico '{service_name}' ja tem {count} instancias"}

        results = {"started": [], "stopped": []}

        if count > current_count:
            # Start additional instances
            for i in range(current_count + 1, count + 1):
                start_result = self.start(service_name)
                # We need to track instance numbers properly
                # Since start() registers with instance=1 by default, we handle scaling differently
                pass
            # Simpler approach: register additional instances directly
            try:
                self.config.load()
            except Exception:
                pass
            svc = self.config.get_service(service_name)
            if not svc:
                return {"success": False, "error": f"Servico '{service_name}' nao encontrado"}

            cmd = self._resolve_start_cmd(service_name, svc)
            if not cmd:
                return {"success": False, "error": f"Nenhum start_cmd para '{service_name}'"}

            port = self._resolve_port(svc)
            env = self._build_env(service_name, svc)
            build_dir = svc.get("build", ".")
            cwd = str(self.project_path / build_dir) if build_dir != "." else str(self.project_path)

            for i in range(current_count + 1, count + 1):
                instance_port = port + (i - 1) if port else None
                if instance_port and is_port_in_use(instance_port):
                    instance_port = get_available_port(instance_port + 1)

                if instance_port:
                    env["PORT"] = str(instance_port)
                    env["GBIT_INSTANCE"] = str(i)

                log_path = self.logs_dir / f"{service_name}_{i}.log"

                try:
                    if sys.platform == "win32":
                        proc = subprocess.Popen(
                            args=cmd, cwd=cwd, env=env,
                            stdout=open(log_path, "a"), stderr=open(log_path, "a"),
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        )
                    else:
                        proc = subprocess.Popen(
                            args=cmd, cwd=cwd, env=env,
                            stdout=open(log_path, "a"), stderr=open(log_path, "a"),
                            start_new_session=True,
                        )

                    cmd_str = " ".join(cmd)
                    self._register_service(service_name, proc.pid, cmd_str, instance_port, instance=i)
                    results["started"].append({"instance": i, "pid": proc.pid, "port": instance_port})
                except Exception as e:
                    results["started"].append({"instance": i, "error": str(e)})

        else:
            # Stop excess instances (highest instance numbers first)
            instances_sorted = sorted(current_instances, key=lambda x: x[1].get("instance", 1), reverse=True)
            for key, entry in instances_sorted[:current_count - count]:
                pid = entry.get("pid")
                if pid and is_process_alive(pid):
                    kill_process(pid)
                self._update_service_status(service_name, "stopped", entry.get("instance", 1))
                results["stopped"].append(key)

        return {"success": True, **results}

    # ── Volume management (directory-based) ────────────────────────

    def volume_create(self, name: str) -> Dict[str, Any]:
        """Create a data volume (directory under .gbit/data/)"""
        vol_path = self.data_dir / name
        vol_path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(vol_path), "name": name}

    def volume_rm(self, name: str) -> Dict[str, Any]:
        """Remove a data volume directory"""
        vol_path = self.data_dir / name
        if not vol_path.exists():
            return {"success": False, "error": f"Volume '{name}' nao encontrado"}
        try:
            shutil.rmtree(vol_path)
            return {"success": True, "name": name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def volume_ls(self) -> List[Dict[str, Any]]:
        """List all data volumes"""
        volumes = []
        if self.data_dir.exists():
            for entry in sorted(self.data_dir.iterdir()):
                if entry.is_dir():
                    try:
                        size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                    except (PermissionError, OSError):
                        size = 0
                    volumes.append({
                        "name": entry.name,
                        "path": str(entry),
                        "size": size,
                        "size_human": f"{size / (1024*1024):.1f} MB" if size >= 1024*1024 else f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B",
                    })
        return volumes

    # ── Network management (localhost no-op) ──────────────────────

    def network_ls(self) -> List[Dict[str, Any]]:
        """List networks — all services on localhost"""
        return [{
            "name": "localhost",
            "type": "native",
            "driver": "host",
            "scope": "local",
            "services": list(self._load_pids().keys()),
        }]

    # ── Image management (service info) ──────────────────────────

    def images(self) -> List[Dict[str, Any]]:
        """List service runtime info (replaces Docker images)"""
        if not self.config.exists():
            return []
        try:
            self.config.load()
        except Exception:
            return []

        all_services = self.config.get_services()
        result = []
        for name, svc in all_services.items():
            result.append({
                "service": name,
                "runtime": svc.get("runtime", "custom"),
                "start_cmd": " ".join(self._resolve_start_cmd(name, svc) or []),
                "build_cmd": " ".join(self._resolve_build_cmd(name, svc) or []),
                "port": self._resolve_port(svc),
                "available": check_binary_available(self._resolve_start_cmd(name, svc)[0]) if self._resolve_start_cmd(name, svc) else False,
            })
        return result

    # ── Pull (no-op) ─────────────────────────────────────────────

    def pull(self, services: Optional[List[str]] = None) -> Dict[str, Any]:
        """Pull is not applicable for process engine — no container images"""
        return {
            "success": True,
            "message": "Process Engine nao utiliza imagens de container. Use 'gbit-container build' para instalar dependencias.",
        }

    # ── Config ──────────────────────────────────────────────────

    def config_show(self) -> Dict[str, Any]:
        """Show current configuration"""
        if not self.config.exists():
            return {"success": False, "error": "gbit.yml nao encontrado"}
        try:
            config = self.config.load()
            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "error": str(e)}
