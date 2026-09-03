'''
ConfigManager v2.0.0 — gbit.yml configuration parser
Accepts start_cmd/command as alternatives to image/build.
No Docker/Podman references.
'''

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import yaml
except ImportError:
    try:
        from yaml import safe_load, safe_dump
    except ImportError:
        yaml = None


def _load_yaml(text: str) -> Any:
    """Load YAML with fallback"""
    if yaml and hasattr(yaml, 'safe_load'):
        return yaml.safe_load(text)
    # Minimal YAML parser fallback
    try:
        return yaml.safe_load(text)
    except Exception:
        raise ImportError("PyYAML necessario. Instale com: pip install pyyaml")


class ConfigManager:
    """Manages gbit.yml configuration — process engine compatible"""

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.config_file = self.project_path / "gbit.yml"
        self._config: Optional[Dict[str, Any]] = None

    def exists(self) -> bool:
        """Check if gbit.yml exists"""
        return self.config_file.exists()

    def load(self) -> Dict[str, Any]:
        """Load and parse gbit.yml"""
        if self._config is not None:
            return self._config

        if not self.exists():
            raise FileNotFoundError(f"gbit.yml nao encontrado em {self.project_path}")

        text = self.config_file.read_text(encoding="utf-8")
        self._config = _load_yaml(text) or {}
        return self._config

    def save(self, config: Dict[str, Any]):
        """Save configuration to gbit.yml"""
        if yaml and hasattr(yaml, 'safe_dump'):
            text = yaml.safe_dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
        else:
            text = str(config)
        self.config_file.write_text(text, encoding="utf-8")
        self._config = config

    def get_project_name(self) -> str:
        """Get project name from config"""
        config = self.load()
        project_meta = config.get("project", {})
        if isinstance(project_meta, dict) and project_meta.get("name"):
            return project_meta.get("name")
        return config.get("name", self.project_path.name)

    def get_services(self) -> Dict[str, Any]:
        """Get all services from config"""
        config = self.load()
        return config.get("services", {})

    def get_service(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific service by name"""
        services = self.get_services()
        return services.get(name)

    def get_volumes(self) -> Dict[str, Any]:
        """Retorna os volumes explicitos do gbit.yml ou mapeia automaticamente a pasta de dados dos servicos."""
        config = self.load()
        volumes = config.get("volumes", {})
        
        if not isinstance(volumes, dict):
            volumes = {}

        # Mapeia volumes de dados automaticos para os servicos definidos
        services = self.get_services()
        for svc_name in services.keys():
            data_dir = self.project_path / ".gbit-container" / "data" / svc_name
            vol_name = f"{svc_name}_data"
            if vol_name not in volumes:
                volumes[vol_name] = {
                    "name": vol_name,
                    "driver": "local",
                    "path": str(data_dir),
                    "service": svc_name
                }
        return volumes

    def to_compose_format(self) -> Dict[str, Any]:
        """Retorna a estrutura formatada do gbit.yml para o endpoint /api/config do Dashboard."""
        config = self.load()
        return {
            "version": config.get("version", config.get("project", {}).get("version", "1.0.0")),
            "name": self.get_project_name(),
            "services": self.get_services(),
            "volumes": self.get_volumes()
        }

    def validate(self) -> List[str]:
        """Validate gbit.yml — services must have start_cmd, command, runtime, image, or build"""
        errors = []

        if not self.exists():
            return []  # Not an error — might be initializing

        try:
            config = self.load()
        except Exception as e:
            return [f"Erro ao carregar gbit.yml: {e}"]

        if not isinstance(config, dict):
            return ["gbit.yml deve ser um dicionario"]

        services = config.get("services", {})
        if not services:
            return []  # Empty services is OK — might be using stacks

        for name, svc in services.items():
            if not isinstance(svc, dict):
                errors.append(f"Servico '{name}': configuracao deve ser um dicionario")
                continue

            # At least ONE of: start_cmd, command, runtime, image, build
            has_start = bool(svc.get("start_cmd") or svc.get("command"))
            has_runtime = bool(svc.get("runtime"))
            has_image = bool(svc.get("image"))  # Legacy compat
            has_build = bool(svc.get("build"))  # Also used as build_dir

            if not any([has_start, has_runtime, has_image, has_build]):
                errors.append(
                    f"Servico '{name}': defina pelo menos um de: start_cmd, command, runtime, image, ou build"
                )

            # Validate port if specified
            port = svc.get("port")
            if port is not None:
                try:
                    int(port)
                except (ValueError, TypeError):
                    errors.append(f"Servico '{name}': porta '{port}' invalida")

            # Validate depends_on
            depends = svc.get("depends_on", [])
            if isinstance(depends, list):
                for dep in depends:
                    if dep not in services:
                        errors.append(f"Servico '{name}': dependencia '{dep}' nao definida")
            elif isinstance(depends, dict):
                for dep in depends.keys():
                    if dep not in services:
                        errors.append(f"Servico '{name}': dependencia '{dep}' nao definida")

        return errors

    def generate_from_stack(self, stack_name: str, stack_data: Dict[str, Any], project_name: Optional[str] = None) -> Dict[str, Any]:
        """Generate gbit.yml config from a stack template"""
        name = project_name or self.project_path.name
        config = {
            "name": name,
            "services": stack_data.get("services", {}),
        }

        # Copy environment overrides
        env_overrides = stack_data.get("environment", {})
        if env_overrides:
            config["environment"] = env_overrides

        return config

     


    def get_networks(self) -> list:
        """Retorna as redes do projeto para o Dashboard."""
        config = self.load()
        project_name = self.get_project_name()

        networks = [
            {
                "name": f"{project_name}_default",
                "driver": "host / loopback",
                "scope": "local",
                "id": "native-loopback-01"
            }
        ]

        # Se houver redes personalizadas declaradas no gbit.yml
        custom_nets = config.get("networks", {})
        if isinstance(custom_nets, dict):
            for net_name, net_info in custom_nets.items():
                driver = net_info.get("driver", "bridge") if isinstance(net_info, dict) else "bridge"
                networks.append({
                    "name": net_name,
                    "driver": driver,
                    "scope": "local",
                    "id": f"net-{net_name}"
                })

        return networks

    def init_project(self, project_name: str, stack_data: Optional[Dict[str, Any]] = None) -> str:
        """Initialize a new gbit.yml project"""
        if stack_data:
            config = self.generate_from_stack(stack_data.get("id", "custom"), stack_data, project_name)
        else:
            config = {
                "name": project_name,
                "services": {
                    "app": {
                        "runtime": "node",
                        "start_cmd": "npm start",
                        "build_cmd": "npm install",
                        "port": 3000,
                        "environment": {
                            "NODE_ENV": "development",
                            "PORT": "3000",
                        },
                    },
                },
            }

        self.save(config)
        return str(self.config_file)