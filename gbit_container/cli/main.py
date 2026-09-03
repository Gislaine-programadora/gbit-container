'''
GBit Container CLI - Main entry point
Modern native process orchestrator (zero Docker/Podman)
'''
import os
import sys
import json
import shutil
import webbrowser
import threading
import signal
from typing import Optional, List

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich import box

from ..__init__ import __version__
from ..core.engine import ProcessEngine, StackFilesMissingError
from ..core.stacks import STACK_TEMPLATES, get_stack_names, get_stack, get_stack_description, resolve_stack_name, get_all_stack_choices
from ..core.runtime import get_system_info, get_system_stats
from ..utils.config import ConfigManager
from colorama import Fore, Style, init

console = Console()


# ========================================================================
# CWD Resolution
# ========================================================================

def _is_gbit_container_source_tree(path: str) -> bool:
    """True only if `path` is unmistakably gbit-container's OWN source
    checkout — never just "any project that happens to have a
    package.json or setup.py" (virtually every Node.js/Python project
    does). The old heuristic checked for package.json/setup.py alone,
    which meant ANY real user's Node project (like a Next.js app) was
    misidentified as "the CLI's own source dir", silently redirecting
    `init`/`stack` output to the wrong directory (in the worst observed
    case, all the way to filesystem root).
    """
    return (
        os.path.isfile(os.path.join(path, "gbit_container", "__init__.py"))
        and os.path.isfile(os.path.join(path, "gbit_container", "cli", "main.py"))
    )


def _resolve_project_cwd() -> str:
    """Return the directory where the user *actually* ran gbit-container.

    Priority order:
      1. GBIT_CWD env-var (set by the Node.js wrapper)
      2. PWD env-var (the shell's idea of cwd), unless it's gbit-container's
         own source tree
      3. os.getcwd(), unless it's gbit-container's own source tree
      4. OLDPWD / HOME fallback (only reached when genuinely inside the
         CLI's own repo, e.g. running `python -m gbit_container...` for
         development)

    NEVER falls back to "/" — a broken HOME/OLDPWD must not silently
    turn into writing project files at the filesystem root.
    """
    explicit = os.environ.get("GBIT_CWD")
    if explicit and os.path.isdir(explicit):
        return os.path.realpath(explicit)

    pwd_env = os.environ.get("PWD")
    if pwd_env and os.path.isdir(pwd_env):
        pwd_real = os.path.realpath(pwd_env)
        if not _is_gbit_container_source_tree(pwd_real):
            return pwd_real

    cwd_real = os.path.realpath(os.getcwd())
    if not _is_gbit_container_source_tree(cwd_real):
        return cwd_real

    # We really are inside gbit-container's own source tree (dev testing
    # without the npm wrapper) — fall back to where the user came from,
    # never to "/".
    fallback = os.environ.get("OLDPWD") or os.environ.get("HOME") or os.path.expanduser("~")
    if fallback and os.path.isdir(fallback) and os.path.realpath(fallback) != "/":
        return os.path.realpath(fallback)

    return cwd_real


def get_project_cwd() -> str:
    """Get the resolved project CWD. Called at runtime, not import-time."""
    return _resolve_project_cwd()

# ========================================================================
# Brand / Banner
# ========================================================================

def print_banner():
    """Banner compacto e moderno do GBit Container.

    "GBIT" em blocos grandes e "CONTAINER" na MESMA linha (texto plano,
    fonte diferente) + selo de versao. ~34 colunas de largura, cabe em
    qualquer terminal 80-col (o wordmark antigo tinha >110 colunas e
    quebrava feio). Sem qualquer referencia a Docker/Podman na marca.
    """
    logo = [
        " ██████╗ ██████╗ ██╗████████╗",
        "██╔════╝ ██╔══██╗██║╚══██╔══╝",
        "██║  ███╗██████╔╝██║   ██║   ",
        "██║   ██║██╔══██╗██║   ██║   ",
        "╚██████╔╝██████╔╝██║   ██║   ",
        " ╚═════╝ ╚═════╝ ╚═╝   ╚═╝   ",
    ]

    console.print()
    for i, line in enumerate(logo):
        text = Text(line, style="bold cyan")
        if i == 2:
            text.append("  CONTAINER", style="bold white")
            text.append(f"  [v{__version__}]", style="bold cyan")
        console.print(text)

    console.print()
    tagline = Text()
    tagline.append("  \u26A1 ", style="bold yellow")
    tagline.append("SISTEMA DE GERENCIAMENTO DE SERVI\u00c7OS", style="dim white")
    tagline.append("  \u2022  ", style="dim")
    tagline.append("CLI", style="bold cyan")
    tagline.append("  \u2022  ", style="dim")
    tagline.append("R\u00c1PIDO", style="bold cyan")
    tagline.append("  \u2022  ", style="dim")
    tagline.append("CONFI\u00c1VEL", style="bold cyan")
    tagline.append("  \u2022  ", style="dim")
    tagline.append("MODERNO", style="bold cyan")
    console.print(tagline)
    console.print()


# Alias para compatibilidade
show_header = print_banner





def _scaffold_template_dir(stack: str) -> Optional[str]:
    """Return the packaged scaffold folder for a stack, if one exists."""
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(pkg_dir, "templates", stack)
    return candidate if os.path.isdir(candidate) else None


def _copy_stack_scaffold(stack: str, project_cwd: str, force: bool) -> List[str]:
    """Copy a stack's packaged scaffold files into the project directory.

    Only writes files that don't already exist, unless force=True. Returns
    the list of files actually written (for the init summary panel).
    """
    src_dir = _scaffold_template_dir(stack)
    if not src_dir:
        return []

    written = []
    for root, _dirs, files in os.walk(src_dir):
        rel_root = os.path.relpath(root, src_dir)
        for fname in files:
            src_file = os.path.join(root, fname)
            rel_path = fname if rel_root == "." else os.path.join(rel_root, fname)
            dest_file = os.path.join(project_cwd, rel_path)

            if os.path.exists(dest_file) and not force:
                continue

            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            shutil.copy2(src_file, dest_file)
            written.append(rel_path)

    return written


def _print_stack_checklist(checklist):
    """Render the checklist before any build call."""
    console.print("[bold cyan][GBit Container][/] Checking stack...")
    for item in checklist:
        if item["exists"]:
            console.print(f"  [green]\u2713[/] {item['service']} -> {item['path']}")
        else:
            console.print(f"  [red]\u2717[/] {item['service']} -> [red]start_cmd nao encontrado[/]")
    console.print()
    missing = [c for c in checklist if not c["exists"]]
    if missing:
        console.print("[bold red]Esperado:[/]")
        for c in missing:
            console.print(f"  {c['path']}")
        console.print()
        console.print(
            "[dim]Dica: rode[/] [bold]gbit-container init --stack <nome> --force[/] "
            "[dim]para gerar os arquivos de exemplo, ou configure o start_cmd no gbit.yml manualmente.[/]"
        )


# ========================================================================
# CLI Group
# ========================================================================

@click.group()
@click.version_option(version=__version__, prog_name="gbit-container", message="%(prog)s %(version)s")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """GBit Container - Modern Process Orchestrator

    A native process orchestrator with dashboard UI.
    Zero Docker/Podman dependencies.
    Start with: gbit-container init
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["engine"] = ProcessEngine(get_project_cwd())


# ========================================================================
# INIT - Initialize a new project
# ========================================================================

@cli.command()
@click.option("--stack", "-s", type=click.Choice(get_all_stack_choices()),
              help="Pre-configured stack template")
@click.option("--name", "-n", help="Project name (default: directory name)")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
@click.option("--interactive", "-i", is_flag=True, help="Interactive setup wizard")
def init(stack, name, force, interactive):
    """Initialize a new gbit-container project"""
    print_banner()

    project_cwd = get_project_cwd()
    config = ConfigManager(project_cwd)

    if config.exists() and not force:
        console.print("[yellow]gbit.yml already exists. Use --force to overwrite.[/]")
        return

    if interactive:
        _interactive_init(name)
        return

    # Use stack template or create minimal
    if stack:
        resolved = resolve_stack_name(stack)
        template = get_stack(resolved)
        console.print(f"[cyan]Using stack:[/] [bold]{resolved}[/] - {template['description']}")
    else:
        # Show available stacks
        console.print("[bold]Available Stack Templates:[/]")
        console.print()

        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Stack", style="bold white")
        table.add_column("Description")
        for sname, stemplate in STACK_TEMPLATES.items():
            table.add_row(sname, stemplate["description"])
        console.print(table)
        console.print()

        choice = click.prompt("Select a stack (or type 'custom')", default="minimal")
        resolved = resolve_stack_name(choice)
        if resolved in STACK_TEMPLATES:
            stack = resolved
            template = get_stack(resolved)
        else:
            template = get_stack("minimal")
            stack = "custom"

    project_name = name or os.path.basename(project_cwd).lower().replace(" ", "-")

    config_data = {
        "project": {
            "name": project_name,
            "description": f"GBit Container project - {stack}",
            "version": "1.0.0",
        },
        "services": template.get("services", {}),
    }

    if "volumes" in template:
        config_data["volumes"] = template["volumes"]
    if "networks" in template:
        config_data["networks"] = template["networks"]

    config.save(config_data)

    # Create .gbit directory
    gbit_dir = os.path.join(project_cwd, ".gbit")
    os.makedirs(gbit_dir, exist_ok=True)

    # Create .env.gbit
    env_path = os.path.join(project_cwd, ".env.gbit")
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write("# GBit Container Environment Variables\n")
            f.write("# Add your environment variables here\n")

    # Copy starter files shipped with the stack, if any.
    scaffolded = _copy_stack_scaffold(resolved, project_cwd, force)

    # Show the ACTUAL absolute paths so the user can verify
    config_abs = os.path.join(project_cwd, "gbit.yml")
    env_abs = os.path.join(project_cwd, ".env.gbit")

    console.print()
    console.print(Panel(
        "[bold green]Project initialized![/]\n\n"
        f"[cyan]Project:[/] {project_name}\n"
        f"[cyan]Stack:[/] {stack}\n"
        f"[cyan]Config:[/] {config_abs}\n"
        f"[cyan]Env:[/] {env_abs}",
        title="[bold]GBit Container[/]",
        border_style="green",
    ))

    if scaffolded:
        console.print("\n[bold]Scaffolded files:[/]")
        for f in scaffolded:
            console.print(f"  [green]\u2713[/] {f}")

    console.print()
    console.print("[dim]Next steps:[/]")
    console.print("  [bold]gbit-container up[/]       [dim]# Start all services[/]")
    console.print("  [bold]gbit-container status[/]   [dim]# Check status[/]")
    console.print("  [bold]gbit-container dashboard[/] [dim]# Open web dashboard[/]")


def _interactive_init(name):
    """Interactive project setup wizard."""
    console.print("[bold cyan]GBit Container Setup Wizard[/]")
    console.print()

    project_cwd = get_project_cwd()
    project_name = name or os.path.basename(project_cwd).lower().replace(" ", "-")

    # Stack selection
    console.print("[bold]Choose a stack template:[/]")
    stacks_list = list(STACK_TEMPLATES.items())
    for i, (sname, stemplate) in enumerate(stacks_list, 1):
        console.print(f"  {i}. [bold]{sname}[/] - {stemplate['description']}")
    console.print(f"  {len(stacks_list) + 1}. Custom (minimal)")

    choice = click.prompt("Select", type=int, default=1)
    if 1 <= choice <= len(stacks_list):
        selected_stack = stacks_list[choice - 1][0]
    else:
        selected_stack = "minimal"

    template = get_stack(selected_stack)

    config_data = {
        "project": {
            "name": project_name,
            "description": f"GBit Container project - {selected_stack}",
            "version": "1.0.0",
        },
        "services": template.get("services", {}),
    }

    if "volumes" in template:
        config_data["volumes"] = template["volumes"]
    if "networks" in template:
        config_data["networks"] = template["networks"]

    config = ConfigManager(project_cwd)
    config.save(config_data)

    # Create .gbit directory
    gbit_dir = os.path.join(project_cwd, ".gbit")
    os.makedirs(gbit_dir, exist_ok=True)

    # Create .env.gbit
    env_path = os.path.join(project_cwd, ".env.gbit")
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write("# GBit Container Environment Variables\n")
            f.write("# Add your environment variables here\n")

    console.print(Panel(
        "[bold green]Project initialized![/]\n\n"
        f"[cyan]Project:[/] {project_name}\n"
        f"[cyan]Stack:[/] {selected_stack}",
        title="[bold]GBit Container[/]",
        border_style="green",
    ))


# ========================================================================
# UP - Start all services
# ========================================================================

@cli.command()
@click.option("--build", "-b", is_flag=True, help="Build before starting")
@click.option("--detach", "-d", is_flag=True, help="Run in background (default)")
@click.option("--service", "-s", "services", multiple=True, help="Specific services to start")
@click.pass_context
def up(ctx, build, detach, services):
    """Start all services"""
    engine = ctx.obj["engine"]

    if build:
        console.print("[cyan]Building...[/]")
        try:
            build_result = engine.build()
            if build_result.get("success"):
                for item in build_result.get("built", []):
                    console.print(f"  [green]\u2713[/] Built {item['service']}")
                for item in build_result.get("skipped", []):
                    console.print(f"  [dim]\u25CB[/] Skipped {item['service']}: {item.get('reason', '')}")
                for item in build_result.get("failed", []):
                    console.print(f"  [red]\u2717[/] Failed {item['service']}: {item.get('error', '')}")
        except Exception as e:
            console.print(f"[red]Build failed: {e}[/]")
            return

    console.print("[cyan]Starting services...[/]")
    try:
        result = engine.up(list(services) if services else None)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if not result.get("success"):
        console.print(f"[red]Failed to start services[/]")
        sys.exit(1)

    started = result.get("started", [])
    failed = result.get("failed", [])
    skipped = result.get("skipped", [])

    for svc in started:
        console.print(f"  [green]\u2713[/] {svc} started")
    for svc in skipped:
        console.print(f"  [yellow]\u25CB[/] {svc} skipped")
    for svc_info in failed:
        svc_name = svc_info if isinstance(svc_info, str) else svc_info.get("service", "unknown")
        console.print(f"  [red]\u2717[/] {svc_name} failed")

    if started:
        console.print()
        console.print(Panel(
            f"[bold green]{len(started)} service(s) started![/]\n\n"
            f"[dim]Use[/] [bold]gbit-container status[/] [dim]to check status[/]\n"
            f"[dim]Use[/] [bold]gbit-container dashboard[/] [dim]to open the web UI[/]",
            title="[bold]GBit Container[/]",
            border_style="green",
        ))
    elif failed:
        console.print()
        console.print(Panel(
            f"[bold red]{len(failed)} service(s) failed to start[/]\n\n"
            f"[dim]Check logs with[/] [bold]gbit-container logs[/]",
            title="[bold]GBit Container[/]",
            border_style="red",
        ))


# ========================================================================
# DOWN - Stop all services
# ========================================================================

@cli.command()
@click.option("--service", "-s", "services", multiple=True, help="Specific services to stop")
@click.pass_context
def down(ctx, services):
    """Stop all services"""
    engine = ctx.obj["engine"]

    console.print("[cyan]Stopping services...[/]")
    try:
        result = engine.down(list(services) if services else None)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    stopped = result.get("stopped", [])
    failed = result.get("failed", [])

    for svc in stopped:
        console.print(f"  [green]\u2713[/] {svc} stopped")
    for svc_info in failed:
        svc_name = svc_info if isinstance(svc_info, str) else svc_info.get("service", "unknown")
        console.print(f"  [red]\u2717[/] {svc_name} stop failed")

    if stopped:
        console.print(Panel(
            f"[bold green]{len(stopped)} service(s) stopped[/]",
            title="[bold]GBit Container[/]",
            border_style="green",
        ))
    elif not failed:
        console.print("[dim]No services running.[/]")


# ========================================================================
# START - Start a specific service
# ========================================================================

@cli.command()
@click.argument("service")
@click.pass_context
def start(ctx, service):
    """Start a specific service"""
    engine = ctx.obj["engine"]

    try:
        result = engine.start(service)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success"):
        pid = result.get("pid", "?")
        port = result.get("port", "?")
        cmd = result.get("cmd", "")
        console.print(Panel(
            f"[bold green]{service} started[/]\n\n"
            f"[cyan]PID:[/] {pid}\n"
            f"[cyan]Port:[/] {port}\n"
            f"[cyan]Command:[/] {cmd}",
            title="[bold]GBit Container[/]",
            border_style="green",
        ))
    else:
        error = result.get("error", result.get("message", "Unknown error"))
        console.print(f"[red]\u2717 {service}: {error}[/]")


# ========================================================================
# STOP - Stop a specific service
# ========================================================================

@cli.command()
@click.argument("service")
@click.pass_context
def stop(ctx, service):
    """Stop a specific service"""
    engine = ctx.obj["engine"]

    try:
        result = engine.stop(service)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success"):
        stopped = result.get("stopped", [])
        console.print(f"[green]\u2713 {service} stopped[/]")
    else:
        console.print(f"[yellow]\u26A0 {service}: {result.get('message', 'Could not stop')}[/]")


# ========================================================================
# RESTART - Restart a specific service
# ========================================================================

@cli.command()
@click.argument("service")
@click.pass_context
def restart(ctx, service):
    """Restart a specific service"""
    engine = ctx.obj["engine"]

    try:
        result = engine.restart(service)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success"):
        pid = result.get("pid", "?")
        port = result.get("port", "?")
        console.print(Panel(
            f"[bold green]{service} restarted[/]\n\n"
            f"[cyan]PID:[/] {pid}\n"
            f"[cyan]Port:[/] {port}",
            title="[bold]GBit Container[/]",
            border_style="green",
        ))
    else:
        console.print(f"[red]\u2717 {service}: restart failed[/]")


# ========================================================================
# PAUSE / UNPAUSE
# ========================================================================

@cli.command()
@click.argument("service")
@click.pass_context
def pause(ctx, service):
    """Pause a running service (sends SIGSTOP)"""
    engine = ctx.obj["engine"]

    try:
        result = engine.pause(service)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success") and not result.get("error"):
        pid = result.get("pid", "?")
        console.print(f"[yellow]\u23F8 {service} paused (PID {pid})[/]")
    else:
        error = result.get("error", result.get("message", "Unknown error"))
        console.print(f"[red]\u2717 {service}: {error}[/]")


@cli.command()
@click.argument("service")
@click.pass_context
def unpause(ctx, service):
    """Unpause a paused service (sends SIGCONT)"""
    engine = ctx.obj["engine"]

    try:
        result = engine.unpause(service)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success") and not result.get("error"):
        pid = result.get("pid", "?")
        console.print(f"[green]\u25B6 {service} unpaused (PID {pid})[/]")
    else:
        error = result.get("error", result.get("message", "Unknown error"))
        console.print(f"[red]\u2717 {service}: {error}[/]")


# ========================================================================
# LOGS - Show service logs
# ========================================================================

@cli.command()
@click.argument("service", required=False)
@click.option("--service", "-s", "service_opt", help="Service name (alternative to positional arg)")
@click.option("--tail", "-t", default=100, help="Number of lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.pass_context
def logs(ctx, service, service_opt, tail, follow):
    """Show service logs.

    Examples:
      gbit-container logs database
      gbit-container logs --service database
      gbit-container logs          (shows every service, one section each)
    """
    engine = ctx.obj["engine"]
    service_name = service or service_opt

    try:
        if service_name:
            result = engine.logs(service_name=service_name, lines=tail, follow=follow)
            _print_log_result(service_name, result)
        else:
            services = engine.config.get_services() if hasattr(engine, "config") else {}
            if not services:
                console.print("[yellow]No services defined in gbit.yml[/]")
                return
            for svc_name in services:
                result = engine.logs(service_name=svc_name, lines=tail, follow=follow)
                _print_log_result(svc_name, result)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)


def _print_log_result(service_name: str, result: dict):
    console.print(f"[bold cyan]--- {service_name} ---[/]")
    if not result.get("success", True):
        console.print(f"[yellow]{result.get('error', 'No logs found')}[/]")
    else:
        for line in result.get("logs", []):
            console.print(line)
        if not result.get("logs"):
            console.print("[dim](sem logs ainda — inicie o servico com 'up' para gerar logs)[/]")
    console.print()


# ========================================================================
# EXEC - Run a command in a service context
# ========================================================================

@cli.command("exec")
@click.argument("service")
@click.argument("command", nargs=-1, required=True)
@click.pass_context
def exec_cmd(ctx, service, command):
    """Run a command in a service context"""
    engine = ctx.obj["engine"]

    cmd_str = " ".join(command)

    try:
        result = engine.exec(service, cmd_str)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success"):
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 0)

        if stdout:
            console.print(stdout)
        if stderr:
            console.print(f"[yellow]{stderr}[/]")
        if exit_code != 0:
            console.print(f"[dim]Exit code: {exit_code}[/]")
            sys.exit(exit_code)
    else:
        error = result.get("error", result.get("message", "Unknown error"))
        console.print(f"[red]\u2717 {service}: {error}[/]")
        sys.exit(1)


# ========================================================================
# PS - List running processes
# ========================================================================

@cli.command("ps")
@click.pass_context
def ps_cmd(ctx):
    """List running services"""
    engine = ctx.obj["engine"]

    try:
        processes = engine.ps()
    except Exception as e:
        console.print(f"[red]{e}[/]")
        return

    if not processes:
        console.print("[dim]No services running.[/]")
        return

    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Name", style="bold")
    table.add_column("Instance")
    table.add_column("PID", style="cyan")
    table.add_column("Status")
    table.add_column("Healthy")
    table.add_column("Port")
    table.add_column("Command", style="dim")
    table.add_column("Started")

    for p in processes:
        status_style = "green" if p.get("status") == "running" else "yellow" if p.get("status") == "paused" else "red"
        healthy_str = "[green]\u2713[/]" if p.get("healthy") else "[red]\u2717[/]"
        port_str = str(p.get("port", "")) if p.get("port") else ""

        table.add_row(
            p.get("name", "?"),
            str(p.get("instance", 1)),
            str(p.get("pid", "?")),
            f"[{status_style}]{p.get('status', '?')}[/]",
            healthy_str,
            port_str,
            p.get("cmd", "")[:60],
            p.get("start_time", ""),
        )

    console.print(table)


# ========================================================================
# BUILD - Build services
# ========================================================================

@cli.command()
@click.option("--service", "-s", "services", multiple=True, help="Specific services to build")
@click.pass_context
def build(ctx, services):
    """Run build commands for services"""
    engine = ctx.obj["engine"]

    console.print("[bold cyan]Building services...[/]")
    try:
        result = engine.build(list(services) if services else None)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success"):
        built = result.get("built", [])
        failed = result.get("failed", [])
        skipped = result.get("skipped", [])

        for item in built:
            console.print(f"  [green]\u2713[/] {item['service']}: {item.get('cmd', 'built')}")
        for item in skipped:
            console.print(f"  [yellow]\u25CB[/] {item['service']}: {item.get('reason', 'skipped')}")
        for item in failed:
            console.print(f"  [red]\u2717[/] {item['service']}: {item.get('error', 'failed')}")

        console.print()
        if built:
            console.print(Panel(
                f"[bold green]{len(built)} service(s) built[/]",
                title="[bold]GBit Container[/]",
                border_style="green",
            ))
        if failed:
            console.print(Panel(
                f"[bold red]{len(failed)} service(s) failed[/]",
                title="[bold]GBit Container[/]",
                border_style="red",
            ))
    else:
        console.print("[red]Build failed[/]")


# ========================================================================
# PULL - Informational (no-op for process engine)
# ========================================================================

@cli.command()
@click.option("--service", "-s", "services", multiple=True, help="Specific services")
@click.pass_context
def pull(ctx, services):
    """Check service dependencies (informational for process engine)"""
    engine = ctx.obj["engine"]

    console.print("[bold cyan]Checking services...[/]")
    try:
        result = engine.pull(list(services) if services else None)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    if result.get("success"):
        msg = result.get("message", "All services ready.")
        console.print(Panel(
            f"[cyan]{msg}[/]\n\n"
            "[dim]Process Engine does not require image pulls.\n"
            "Services run as native OS processes directly.[/]",
            title="[bold]GBit Container[/]",
            border_style="cyan",
        ))


# ========================================================================
# IMAGES - Show service runtime info
# ========================================================================

@cli.command()
@click.pass_context
def images(ctx):
    """Show service runtime information"""
    engine = ctx.obj["engine"]

    try:
        result = engine.images()
    except Exception as e:
        console.print(f"[red]{e}[/]")
        return

    if not result:
        console.print("[dim]No services configured.[/]")
        return

    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Service", style="bold")
    table.add_column("Runtime")
    table.add_column("Start Command")
    table.add_column("Build Command")
    table.add_column("Port")
    table.add_column("Available")

    for item in result:
        avail_str = "[green]\u2713[/]" if item.get("available") else "[red]\u2717[/]"
        table.add_row(
            item.get("service", "?"),
            item.get("runtime", "-"),
            item.get("start_cmd", "-")[:50],
            item.get("build_cmd", "-")[:50],
            str(item.get("port", "-")),
            avail_str,
        )

    console.print(table)


# ========================================================================
# DASHBOARD - Web UI
# ========================================================================

@cli.command()
@click.option("--port", "-p", default=7890, help="Dashboard port")
@click.option("--host", "-h", default="0.0.0.0", help="Dashboard host")
@click.option("--open", "-o", "open_browser", is_flag=True, help="Auto-open in browser")
@click.pass_context
def dashboard(ctx, port, host, open_browser):
    """Open the GBit Container Dashboard"""
    print_banner()
    console.print("[bold cyan]Starting GBit Container Dashboard...[/]")

    project_cwd = get_project_cwd()

    try:
        from ..dashboard.app import create_dashboard_app
        app = create_dashboard_app(project_cwd)

        console.print(f"[green]Dashboard running at:[/] [bold underline]http://localhost:{port}[/]")
        console.print("[dim]Press Ctrl+C to stop[/]")
        console.print()

        if open_browser:
            def open_url():
                import time
                time.sleep(1.5)
                webbrowser.open(f"http://localhost:{port}")
            threading.Thread(target=open_url, daemon=True).start()

        app.run(host=host, port=port, debug=False, use_reloader=False)

    except ImportError as e:
        console.print(f"[red]Dashboard dependencies missing: {e}[/]")
        console.print("[dim]Install with: pip install flask[/]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/]")


# ========================================================================
# STATUS / STATS / INSPECT
# ========================================================================

@cli.command()
@click.pass_context
def status(ctx):
    """Show project status"""
    engine = ctx.obj["engine"]

    try:
        result = engine.status()
    except Exception:
        result = {"engine": "unknown", "version": __version__, "available": False,
                  "total_services": 0, "running": 0, "stopped": 0, "paused": 0,
                  "project": "unknown", "project_path": "unknown"}

    if not result.get("available", True):
        console.print(Panel(
            "[bold red]gbit-container engine not available[/]\n\n"
            "[dim]Check your gbit.yml and .env.gbit configuration.[/]",
            title="[bold]GBit Container[/]",
            border_style="red",
        ))
        return

    running = result.get("running", 0)
    stopped = result.get("stopped", 0)
    paused = result.get("paused", 0)
    total = result.get("total_services", 0)

    if running > 0:
        status_color = "green"
        status_text = "running"
    elif paused > 0:
        status_color = "yellow"
        status_text = "paused"
    else:
        status_color = "red"
        status_text = "stopped"

    console.print(Panel(
        f"[bold]Engine:[/] {result.get('engine', 'ProcessEngine')} v{result.get('version', __version__)}\n"
        f"[bold]Project:[/] {result.get('project', 'unknown')}\n"
        f"[bold]Status:[/] [{status_color}]{status_text}[/]\n"
        f"[bold]Services:[/] {running} running / {paused} paused / {stopped} stopped / {total} total",
        title="[bold]GBit Container Status[/]",
        border_style=status_color,
    ))


@cli.command()
@click.pass_context
def stats(ctx):
    """Show resource usage stats"""
    engine = ctx.obj["engine"]

    try:
        result = engine.stats()
    except Exception as e:
        console.print(f"[yellow]{e}[/]")
        return

    if not result.get("success"):
        console.print("[dim]No running services.[/]")
        return

    # ProcessEngine.stats() returns a dict with 'services' list or single service info
    services_list = result.get("services", [])
    if not services_list:
        # Single service stats
        if result.get("service"):
            services_list = [result]
        else:
            console.print("[dim]No running services.[/]")
            return

    table = Table(title="Service Stats", show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Service", style="bold")
    table.add_column("PID")
    table.add_column("CPU %")
    table.add_column("Memory")
    table.add_column("Mem %")
    table.add_column("Status")

    for s in services_list:
        status_style = "green" if s.get("status") == "running" else "yellow"
        table.add_row(
            s.get("service", s.get("name", "?")),
            str(s.get("pid", "?")),
            f"{s.get('cpu_percent', 0):.1f}",
            s.get("memory_human", "?"),
            f"{s.get('memory_percent', 0):.1f}",
            f"[{status_style}]{s.get('status', '?')}[/]",
        )

    console.print(table)


@cli.command()
@click.argument("service")
@click.pass_context
def inspect(ctx, service):
    """Inspect a service"""
    engine = ctx.obj["engine"]

    try:
        info = engine.inspect(service)
        console.print_json(json.dumps(info, indent=2))
    except Exception as e:
        console.print(f"[red]{e}[/]")


# ========================================================================
# CONFIG / VALIDATE / SCALE
# ========================================================================

@cli.command(name="config")
@click.option("--validate", is_flag=True, help="Validate the configuration")
@click.option("--show", is_flag=True, help="Show parsed configuration")
@click.pass_context
def config_cmd(ctx, validate, show):
    """Show or validate configuration"""
    project_cwd = get_project_cwd()
    config = ConfigManager(project_cwd)

    if validate:
        errors = config.validate()
        if errors:
            console.print("[red]Configuration errors:[/]")
            for err in errors:
                console.print(f"  [red]- {err}[/]")
        else:
            console.print("[green]Configuration is valid[/]")
        return

    if show:
        try:
            compose = config.to_compose_format()
            console.print_json(json.dumps(compose, indent=2))
        except Exception as e:
            console.print(f"[red]{e}[/]")
        return

    try:
        data = config.load()
        console.print_json(json.dumps(data, indent=2))
    except FileNotFoundError:
        console.print("[yellow]gbit.yml not found. Run 'gbit-container init' first.[/]")


@cli.command()
@click.argument("service")
@click.argument("replicas", type=int)
@click.pass_context
def scale(ctx, service, replicas):
    """Scale a service"""
    engine = ctx.obj["engine"]

    try:
        result = engine.scale(service, replicas)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        return

    if result.get("success"):
        started = result.get("started", [])
        stopped = result.get("stopped", [])
        console.print(f"[green]Scaled {service} to {replicas} instance(s)[/]")
        for s in started:
            console.print(f"  [green]\u2713[/] Started instance: {s}")
        for s in stopped:
            console.print(f"  [yellow]\u25CB[/] Stopped instance: {s}")
    else:
        console.print(f"[red]Failed to scale {service}[/]")


# ========================================================================
# VOLUME commands
# ========================================================================

@cli.group()
def volume():
    """Manage volumes"""
    pass


@volume.command(name="ls")
@click.pass_context
def volume_ls(ctx):
    """List project volumes"""
    engine = ctx.obj["engine"]

    try:
        engine.initialize()
        volumes = engine.volume_ls()
        if not volumes:
            console.print("[dim]No volumes found.[/]")
            return
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Name", style="bold")
        table.add_column("Path")
        table.add_column("Size")
        for v in volumes:
            table.add_row(v["name"], v.get("path", "-"), v.get("size_human", v.get("size", "?")))
        console.print(table)
    except Exception as e:
        console.print(f"[yellow]{e}[/]")


@volume.command(name="create")
@click.argument("name")
@click.pass_context
def volume_create(ctx, name):
    """Create a volume"""
    engine = ctx.obj["engine"]

    try:
        engine.initialize()
        result = engine.volume_create(name)
        if result.get("success"):
            console.print(f"[green]Volume created: {result['name']}[/]")
            console.print(f"  [dim]Path:[/] {result.get('path', '?')}")
        else:
            console.print(f"[red]Failed to create volume: {result.get('error', 'unknown error')}[/]")
    except Exception as e:
        console.print(f"[red]{e}[/]")


@volume.command(name="rm")
@click.argument("name")
@click.pass_context
def volume_rm(ctx, name):
    """Remove a volume"""
    engine = ctx.obj["engine"]

    try:
        engine.initialize()
        result = engine.volume_rm(name)
        if result.get("success") and not result.get("error"):
            console.print(f"[green]Volume removed: {result['name']}[/]")
        else:
            error = result.get("error", "unknown error")
            console.print(f"[red]Failed to remove volume: {error}[/]")
    except Exception as e:
        console.print(f"[red]{e}[/]")


# ========================================================================
# STACK - Shortcut: `gbit-container stack <name>` == `init --stack <name>`
# ========================================================================

@cli.command(name="stack")
@click.argument("name", type=click.Choice(get_all_stack_choices()))
@click.option("--project-name", "-n", "proj_name", help="Project name (default: directory name)")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
@click.pass_context
def stack_cmd(ctx, name, proj_name, force):
    """Apply a stack template to the current folder.

    Shortcut for `gbit-container init --stack <name>` — same effect,
    shorter to type: `gbit-container stack gbit-db`.
    """
    ctx.invoke(init, stack=name, name=proj_name, force=force, interactive=False)


# ========================================================================
# NETWORK commands
# ========================================================================

@cli.group()
def network():
    """Manage networks"""
    pass


@network.command(name="ls")
@click.pass_context
def network_ls(ctx):
    """List project networks"""
    engine = ctx.obj["engine"]

    try:
        engine.initialize()
        networks = engine.network_ls()
        if not networks:
            console.print("[dim]No project networks found.[/]")
            return
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Name", style="bold")
        table.add_column("Type")
        table.add_column("Driver")
        table.add_column("Scope")
        table.add_column("Services", style="dim")
        for n in networks:
            svc_list = ", ".join(n.get("services", []))
            table.add_row(n["name"], n.get("type", "-"), n.get("driver", "-"), n.get("scope", "-"), svc_list)
        console.print(table)
    except Exception as e:
        console.print(f"[yellow]{e}[/]")


# ========================================================================
# STACKS - List available stack templates
# ========================================================================

@cli.command()
@click.pass_context
def stacks(ctx):
    """Show available stack templates"""
    print_banner()

    table = Table(title="Available Stack Templates", show_header=True,
                  header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Stack", style="bold white")
    table.add_column("Description")
    table.add_column("Services", style="dim")

    for name, template in STACK_TEMPLATES.items():
        services = ", ".join(template.get("services", {}).keys())
        table.add_row(name, template["description"], services)

    console.print(table)
    console.print("\n[dim]Use: gbit-container init --stack <name>[/]")


# ========================================================================
# INFO - System info
# ========================================================================

@cli.command()
@click.pass_context
def info(ctx):
    """Show system and engine info"""
    print_banner()

    sys_info = get_system_info()
    sys_stats = get_system_stats()

    info_table = Table(show_header=False, box=box.ROUNDED, border_style="cyan")
    info_table.add_column("Key", style="bold cyan")
    info_table.add_column("Value")

    info_table.add_row("GBit Container", __version__)
    info_table.add_row("Engine", "ProcessEngine (Native)")
    info_table.add_row("Platform", sys_info.get("platform", "unknown"))
    info_table.add_row("Architecture", sys_info.get("architecture", "unknown"))
    info_table.add_row("Python", sys_info.get("python_version", "unknown"))

    # System stats
    if sys_stats:
        cpu = sys_stats.get("cpu_percent", "?")
        mem = sys_stats.get("memory", {})
        mem_total = mem.get("total_human", "?") if isinstance(mem, dict) else "?"
        mem_avail = mem.get("available_human", "?") if isinstance(mem, dict) else "?"
        info_table.add_row("System CPU", f"{cpu}%" if isinstance(cpu, (int, float)) else str(cpu))
        info_table.add_row("System Memory", f"{mem_avail} / {mem_total}")

    import gbit_container as _gc
    info_table.add_row("Loaded from", os.path.dirname(os.path.abspath(_gc.__file__)))

    project_cwd = get_project_cwd()
    config = ConfigManager(project_cwd)
    if config.exists():
        try:
            config.load()
            info_table.add_row("Project", config.get_project_name())
            info_table.add_row("Services", str(len(config.get_services())))
        except Exception:
            info_table.add_row("Config", "[yellow]Error reading gbit.yml[/]")
    else:
        info_table.add_row("Project", "[dim]Not initialized[/]")

    console.print(Panel(info_table, title="[bold]System Info[/]", border_style="cyan"))


# ========================================================================
# SHELL - Open a shell in a service context
# ========================================================================

@cli.command()
@click.argument("service")
@click.pass_context
def shell(ctx, service):
    """Open an interactive shell in a service context"""
    engine = ctx.obj["engine"]

    try:
        result = engine.shell(service)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    # shell() starts an interactive session; if it returns dict, show info
    if isinstance(result, dict):
        if result.get("success"):
            console.print(f"[green]Shell session ended for {service}[/]")
        else:
            error = result.get("error", result.get("message", "Unknown error"))
            console.print(f"[red]Shell failed for {service}: {error}[/]")


# ========================================================================
# MAIN
# ========================================================================

if __name__ == "__main__":
    cli()
