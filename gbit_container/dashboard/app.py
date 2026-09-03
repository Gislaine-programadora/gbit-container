'''
GBit Container Dashboard - Flask Web App
Modern web dashboard for native process management

v2.0.0 — ProcessEngine-based: no Docker/Podman required.
Services run as native subprocesses with PID tracking.
'''
import os
import json
from typing import Optional

from flask import Flask, render_template, jsonify, request

from ..core.engine import ProcessEngine
from ..core.stacks import STACK_TEMPLATES, STACK_ALIASES
from ..core.runtime import get_system_info, get_system_stats
from ..utils.config import ConfigManager
from .. import __version__


def create_dashboard_app(project_path: Optional[str] = None):
    """Create and configure the Flask dashboard app"""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    cwd = project_path or os.getcwd()

    # ── Helpers ─────────────────────────────────────────────

    def _get_engine():
        return ProcessEngine(cwd)

    def _get_config():
        return ConfigManager(cwd)

    # ── Routes ───────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    @app.route("/api/status")
    def api_status():
        try:
            engine = _get_engine()
            result = engine.status()
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/system")
    def api_system():
        """System information endpoint for the dashboard.

        Returns CPU, memory, disk stats plus engine info.
        The ProcessEngine is always available (native OS processes)
        so engine_available is always True.
        """
        try:
            sys_info = get_system_info()
            sys_stats = get_system_stats()

            result = {
                "cpu_percent": sys_stats.get("cpu_percent", 0),
                "memory": sys_stats.get("memory", {
                    "percent": 0, "used": 0, "total": 0, "available": 0
                }),
                "disk": sys_stats.get("disk", {
                    "percent": 0, "used": 0, "total": 0, "free": 0
                }),
                "engine_available": True,
                "engine_type": "process_engine",
                "engine_version": __version__,
                "platform": sys_info.get("platform", "Unknown"),
                "architecture": sys_info.get("architecture", "Unknown"),
                "python_version": sys_info.get("python_version", "Unknown"),
                "gbit_version": __version__,
            }
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/stacks")
    def api_stacks():
        """Available stack templates for the dashboard."""
        try:
            stacks = []
            for name, template in STACK_TEMPLATES.items():
                services = list(template.get("services", {}).keys())
                stacks.append({
                    "name": name,
                    "description": template.get("description", ""),
                    "services": services,
                })
            return jsonify({"success": True, "data": stacks})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/containers")
    def api_containers():
        try:
            engine = _get_engine()
            containers = engine.ps()
            return jsonify({"success": True, "data": containers})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/stats")
    def api_stats():
        try:
            engine = _get_engine()
            stats = engine.stats()
            return jsonify({"success": True, "data": stats})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/services")
    def api_services():
        try:
            config = _get_config()
            config.load()
            services = config.get_services()
            result = []
            for name, svc in services.items():
                result.append({
                    "name": name,
                    "command": svc.get("start_cmd", "") or svc.get("command", "") or "custom",
                    "runtime": svc.get("runtime", "native"),
                    "ports": svc.get("ports", []),
                    "status": "defined",
                })
            return jsonify({"success": True, "data": result})
        except FileNotFoundError:
            return jsonify({"success": True, "data": [], "config_missing": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/config")
    def api_config():
        try:
            config = _get_config()
            config.load()
            data = config.to_compose_format()
            return jsonify({"success": True, "data": data})
        except FileNotFoundError:
            return jsonify({"success": True, "data": {}, "config_missing": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ── Action endpoints ────────────────────────────────────

    @app.route("/api/action/up", methods=["POST"])
    def action_up():
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.up(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/down", methods=["POST"])
    def action_down():
        try:
            engine = _get_engine()
            result = engine.down()
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/restart", methods=["POST"])
    def action_restart():
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.restart(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/stop", methods=["POST"])
    def action_stop():
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.stop(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/pause", methods=["POST"])
    def action_pause():
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.pause(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/unpause", methods=["POST"])
    def action_unpause():
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.unpause(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/build", methods=["POST"])
    def action_build():
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.build(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/pull", methods=["POST"])
    def action_pull():
        """Pull/install dependencies for specified services.

        With ProcessEngine, 'pull' installs npm/pip/etc. dependencies
        for services that have a build_cmd or start_cmd that requires them.
        """
        try:
            engine = _get_engine()
            services = request.json.get("services") if request.json else None
            result = engine.pull(services=services)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/action/logs", methods=["GET"])
    def action_logs():
        try:
            engine = _get_engine()
            service = request.args.get("service")
            tail = request.args.get("tail", 100, type=int)
            result = engine.logs(service_name=service, lines=tail)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/networks")
    def api_networks():
        """Live port/connectivity map for the project's services.

        With ProcessEngine there's no virtual Docker network to inspect
        — services just bind to localhost ports. This repurposes the
        "Network" tab into something actually useful for that model:
        which port each service uses, whether something is really
        listening on it right now, and a direct link to open it.
        """
        try:
            from ..core.runtime import check_port_connectivity

            engine = _get_engine()
            processes = engine.ps()

            entries = []
            for proc in processes:
                port = proc.get("port")
                listening = bool(port) and check_port_connectivity(int(port))
                entries.append({
                    "name": proc.get("service") or proc.get("name"),
                    "port": port,
                    "url": f"http://localhost:{port}" if port else None,
                    "listening": listening,
                    "status": proc.get("status", "stopped"),
                })

            return jsonify({"success": True, "data": {"services": entries}})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    def _http_probe(url: str, method: str = "GET", timeout: float = 3.0, body: Optional[str] = None):
        """Make a real HTTP request server-side and return a small, safe summary.

        Done server-side (not from the browser) so this never runs into
        CORS restrictions from the target service — the dashboard's own
        origin never talks to the service directly, only this endpoint does.
        """
        import time
        import urllib.request
        import urllib.error

        start = time.time()
        try:
            data = body.encode("utf-8") if body else None
            req = urllib.request.Request(url, data=data, method=method.upper())
            if data:
                req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                elapsed_ms = round((time.time() - start) * 1000)
                raw = resp.read(4096)
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception:
                    text = repr(raw)
                return {
                    "ok": True,
                    "status_code": resp.status,
                    "elapsed_ms": elapsed_ms,
                    "content_type": resp.headers.get("Content-Type", ""),
                    "body": text[:2000],
                }
        except urllib.error.HTTPError as e:
            elapsed_ms = round((time.time() - start) * 1000)
            raw = e.read(4096) if hasattr(e, "read") else b""
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                text = ""
            return {
                "ok": False,
                "status_code": e.code,
                "elapsed_ms": elapsed_ms,
                "content_type": "",
                "body": text[:2000],
                "error": str(e),
            }
        except Exception as e:
            elapsed_ms = round((time.time() - start) * 1000)
            return {
                "ok": False,
                "status_code": None,
                "elapsed_ms": elapsed_ms,
                "content_type": "",
                "body": "",
                "error": str(e),
            }

    @app.route("/api/apis")
    def api_apis():
        """Auto-discovery: probe the root ('/') of every running service.

        Gives an at-a-glance "is this service's HTTP endpoint actually
        answering" view, without the user needing to open each URL by
        hand or reach for curl/Postman.
        """
        try:
            engine = _get_engine()
            processes = engine.ps()

            entries = []
            for proc in processes:
                port = proc.get("port")
                name = proc.get("service") or proc.get("name")
                if not port:
                    entries.append({"name": name, "port": None, "url": None, "root": None})
                    continue

                base_url = f"http://localhost:{port}"
                probe = None
                if proc.get("status") == "running":
                    probe = _http_probe(base_url + "/", timeout=2.0)

                entries.append({
                    "name": name,
                    "port": port,
                    "url": base_url,
                    "root": probe,
                    "service_status": proc.get("status", "stopped"),
                })

            return jsonify({"success": True, "data": {"services": entries}})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/apis/test", methods=["POST"])
    def api_apis_test():
        """Manual API tester: send a real request to <service>:<port><path>."""
        try:
            payload = request.json or {}
            service = payload.get("service")
            path = payload.get("path") or "/"
            method = (payload.get("method") or "GET").upper()
            body = payload.get("body")

            if not service:
                return jsonify({"success": False, "error": "service is required"})

            config = _get_config()
            config.load()
            services = config.get_services()
            svc = services.get(service)
            if not svc:
                return jsonify({"success": False, "error": f"Service '{service}' not found in gbit.yml"})

            port = svc.get("port")
            if not port:
                return jsonify({"success": False, "error": f"Service '{service}' has no port configured"})

            if not path.startswith("/"):
                path = "/" + path
            url = f"http://localhost:{port}{path}"

            result = _http_probe(url, method=method, timeout=5.0, body=body)
            result["url"] = url
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    return app


if __name__ == "__main__":
    app = create_dashboard_app(os.getcwd())
    app.run(host="0.0.0.0", port=7890, debug=True)
