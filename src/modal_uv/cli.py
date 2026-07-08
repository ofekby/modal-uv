"""Typer CLI for modal-uv."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from modal_uv.client import daemon_status, ensure_daemon, send_request, stop_daemon
from modal_uv.config import ConfigError, ModalUVConfig, ProjectContext, load_config, resolve_project
from modal_uv.deployment import (
    DeploymentBroken,
    DeploymentMissing,
    deploy_generated_artifact,
    deployment_fingerprint,
    deployment_parameters,
    load_deployment_template,
    query_deployed_fingerprint,
    render_deployment,
    write_deployment_artifact,
)
from modal_uv.paths import ensure_repo_state
from modal_uv.skill import KNOWN_AGENTS, install_to_agent, install_to_all_present, install_to_dir
from modal_uv.sync import TrackingConfig, build_manifest

app = typer.Typer(
    name="modal-uv",
    help="Run uv commands on Modal.com with GPU and direct file sync.",
)


@app.command()
def run(
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Arguments passed to uv."),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Stream deployment output to terminal."),
    ] = False,
) -> None:
    """Execute uv <args> on Modal with GPU."""
    uv_args = args or []
    try:
        project, config = _load_project_config(config_path)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    try:
        _ensure_deployment_with_notice(config, project.repo_root, verbose=verbose)
        manifest = build_manifest(project.repo_root, _load_tracking_config(config))
        expected_fp = _compute_expected_fingerprint(config, project.repo_root)

        execution_id = _sync_and_spawn(
            project, manifest, uv_args, expected_fp, _restart_attempted=False
        )

        typer.echo(f"Execution ID: {execution_id}")
        typer.echo(f"Tail logs: modal-uv logs {execution_id}")
        typer.echo(f"Abort: modal-uv abort {execution_id}")
        raise SystemExit(0)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@app.command()
def logs(
    execution_id: Annotated[str, typer.Argument(help="Modal FunctionCall ID to tail.")],
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Print logs for a spawned execution and wait for it to complete."""
    try:
        _project, config = _load_project_config(config_path)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "modal",
            "app",
            "logs",
            config.app_name,
            "--function-call",
            execution_id,
            "--follow",
        ]
    )
    try:
        import modal

        return_code = modal.FunctionCall.from_id(execution_id).get()
        time.sleep(1)
    except KeyboardInterrupt:
        process.terminate()
        raise SystemExit(130) from None
    except Exception as exc:
        process.terminate()
        typer.echo(f"Error waiting for function call: {exc}", err=True)
        raise SystemExit(1) from exc
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    raise SystemExit(return_code if isinstance(return_code, int) else 0)


@app.command()
def abort(
    execution_id: Annotated[str, typer.Argument(help="Modal FunctionCall ID to cancel.")],
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Abort a spawned execution."""
    try:
        import modal

        _load_project_config(config_path)
        function_call = modal.FunctionCall.from_id(execution_id)
        function_call.cancel()
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    typer.echo(f"Aborted: {execution_id}")
    raise SystemExit(0)


@app.command()
def shell(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Open an interactive shell on Modal."""
    try:
        _project, config = _load_project_config(config_path)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    cmd = [
        sys.executable,
        "-m",
        "modal",
        "shell",
    ]
    for vol in config.volumes:
        cmd.extend(["--volume", vol.name])
    if config.gpu is not None:
        cmd[2:2] = ["--gpu", config.gpu]

    try:
        result = subprocess.run(cmd)
        raise SystemExit(result.returncode)
    except KeyboardInterrupt:
        raise SystemExit(0) from None


@app.command()
def status(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Show Modal app status."""
    try:
        _project, config = _load_project_config(config_path)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    cmd = [sys.executable, "-m", "modal", "app", "list", "--json"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            typer.echo(f"Error: {result.stderr}", err=True)
            raise SystemExit(1)

        apps = json.loads(result.stdout)
        matching = [a for a in apps if a.get("Description") == config.app_name]

        if not matching:
            typer.echo(f"No app found with name: {config.app_name}")
            raise SystemExit(1)

        for a in matching:
            typer.echo(f"App: {a['Description']}")
            typer.echo(f"  Status: {a.get('State', 'unknown')}")
            typer.echo(f"  ID: {a.get('App ID', 'unknown')}")

        raise SystemExit(0)
    except json.JSONDecodeError:
        typer.echo("Error: failed to parse app list output", err=True)
        raise SystemExit(1) from None


@app.command()
def daemon_stop(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Stop the modal-uv daemon."""
    try:
        project, _config = _load_project_config(config_path)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
    if stop_daemon(project.repo_root):
        typer.echo("Daemon stopped.")
    else:
        typer.echo("No daemon running.")


@app.command()
def daemon_status_cmd(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Show modal-uv daemon status."""
    try:
        project, _config = _load_project_config(config_path)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
    info = daemon_status(project.repo_root)
    if info is None:
        typer.echo("Daemon not running.")
    else:
        typer.echo(f"Daemon running: pid={info['pid']} sock={info['socket']}")


@app.command()
def whoami() -> None:
    """Show the authenticated Modal user."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "modal", "profile", "current"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    if result.returncode != 0:
        typer.echo("Not authenticated.")
        raise SystemExit(0)

    output = result.stdout.strip()
    if not output:
        output = result.stderr.strip()
    typer.echo(output)
    raise SystemExit(0)


@app.command()
def doctor(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to modal-uv.yaml config file."),
    ] = None,
) -> None:
    """Show modal-uv health vitals without waking the container."""
    typer.echo("modal-uv doctor")
    typer.echo("---")

    try:
        project = resolve_project(config_path)
        config = load_config(project.config_path)
    except ConfigError:
        typer.echo("Config: modal-uv.yaml not found in current directory or parents")
        typer.echo("Run 'modal-uv init' to create one.")
        raise SystemExit(0) from None

    typer.echo(f"Config: {project.config_path}")

    auth_ok, auth_info = _check_auth()
    typer.echo(f"Auth: {auth_info}")

    for vol in config.volumes:
        volume_ok, volume_info = _check_volume(vol.name)
        typer.echo(f"Volume ({vol.name}): {volume_info}")

    app_ok, app_info = _check_app(config.app_name)
    typer.echo(f"App ({config.app_name}): {app_info}")

    daemon_info = daemon_status(project.repo_root)
    if daemon_info is not None:
        typer.echo(f"Daemon: running (pid={daemon_info['pid']})")
    else:
        typer.echo("Daemon: not running")

    raise SystemExit(0)


def _check_auth() -> tuple[bool, str]:
    """Check Modal authentication state."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "modal", "profile", "current"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "unable to check"
    if result.returncode != 0:
        return False, "not authenticated"
    output = result.stdout.strip() or result.stderr.strip()
    return True, output if output else "authenticated"


def _check_volume(volume_name: str) -> tuple[bool, str]:
    """Check if a Modal volume exists."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "modal", "volume", "ls", volume_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "unable to check"
    if result.returncode != 0:
        return False, "unable to list volumes"
    return True, "exists"


def _check_app(app_name: str) -> tuple[bool, str]:
    """Check if a Modal app deployment exists."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "modal", "app", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "unable to check"
    if result.returncode != 0:
        return False, "unable to list apps"
    try:
        apps = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "unable to parse app list"
    for a in apps:
        if a.get("Description") == app_name:
            state = a.get("State", "unknown")
            return True, f"deployed ({state})"
    return False, "not deployed"


@app.command()
def init() -> None:
    """Initialize or align modal-uv files in the current directory."""
    repo_root = Path.cwd()
    config_file = repo_root / "modal-uv.yaml"

    if not config_file.exists():
        default_name = repo_root.name or "my-project"
        config_file.write_text(_default_config(default_name), encoding="utf-8")
        typer.echo(f"Created {config_file}")
    else:
        typer.echo(f"Found existing {config_file}")

    ensure_repo_state(repo_root)
    typer.echo(f"Ensured {repo_root / '.modal-uv'}")
    typer.echo("Done.")
    raise SystemExit(0)


@app.command()
def onboard() -> None:
    """Run Modal OAuth setup and install the skill to detected agents."""
    exit_code = _run_modal_oauth()
    if exit_code != 0:
        raise SystemExit(exit_code)

    paths = install_to_all_present()
    if paths:
        for p in paths:
            typer.echo(f"Installed skill: {p}")
    else:
        typer.echo(
            "No agents detected. Use 'modal-uv install-skill <agent|path>' to install manually."
        )
    raise SystemExit(0)


@app.command()
def update() -> None:
    """Upgrade modal-uv and refresh the skill on detected agents."""
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "modal-uv"])
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    paths = install_to_all_present()
    if paths:
        for p in paths:
            typer.echo(f"Updated skill: {p}")
    else:
        typer.echo(
            "No agents detected. Use 'modal-uv install-skill <agent|path>' to install manually."
        )
    raise SystemExit(0)


@app.command(name="install-skill")
def install_skill(
    target: Annotated[
        str,
        typer.Argument(help="Agent name (opencode, claude, agents) or explicit directory path."),
    ],
) -> None:
    """Install the modal-uv skill to a specific agent or path."""
    if target in KNOWN_AGENTS:
        path = install_to_agent(target)
    else:
        path = install_to_dir(Path(target).expanduser())
    typer.echo(f"Installed skill: {path}")
    raise SystemExit(0)


@app.command(name="modal")
def modal_cmd(
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Arguments passed to modal CLI."),
    ] = None,
) -> None:
    """Run modal CLI commands through the modal-uv environment."""
    modal_args = args or []
    if not modal_args:
        typer.echo("Error: modal arguments required", err=True)
        raise SystemExit(2)
    try:
        result = subprocess.run([sys.executable, "-m", "modal", *modal_args])
        raise SystemExit(result.returncode)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


def _load_project_config(config_path: Path | None) -> tuple[ProjectContext, ModalUVConfig]:
    project = resolve_project(config_path)
    config = load_config(project.config_path)
    ensure_repo_state(project.repo_root)
    return project, config


def _load_tracking_config(config: ModalUVConfig) -> TrackingConfig:
    return TrackingConfig(ignore=config.sync.ignore)


def _default_config(app_name: str) -> str:
    return f"""\
app_name: "{app_name}"
gpu: "T4"
work_dir: "/tmp/work"

volumes:
  - name: "modal-uv-cache"
    mount_path: "/mnt/volume"
    commit_interval_seconds: 30

env: {{}}

image:
  python_version: "3.12"
  base_image: "python:3.12-slim"

sync:
  ignore: []
"""


def _open_url(url: str) -> bool:
    """Open URL in browser using WSL-compatible methods. Returns True if opened."""
    import shutil
    import webbrowser

    if shutil.which("wslview"):
        try:
            subprocess.run(["wslview", url], check=False, timeout=10)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    if shutil.which("cmd.exe"):
        try:
            subprocess.run(["cmd.exe", "/c", "start", "", url], check=False, timeout=10)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    try:
        if webbrowser.open(url):
            return True
    except Exception:
        pass

    if shutil.which("xdg-open"):
        try:
            subprocess.run(["xdg-open", url], check=False, timeout=10)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return False


def _run_modal_oauth() -> int:
    """Run modal token new, detect OAuth URL, open browser. Returns exit code."""
    import re

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "modal", "token", "new", "--activate", "--verify"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    url_pattern = re.compile(r"https://modal\.com/token-flow/\S+")
    url_opened = False

    if process.stdout is None:
        typer.echo("Error: failed to capture modal token output", err=True)
        return 1

    for line in process.stdout:
        sys.stderr.write(line)
        if not url_opened:
            match = url_pattern.search(line)
            if match:
                url = match.group(0)
                if _open_url(url):
                    typer.echo(f"[modal-uv] Opened browser: {url}", err=True)
                else:
                    typer.echo(f"[modal-uv] Open this URL manually: {url}", err=True)
                url_opened = True

    return process.wait()


def _compute_expected_fingerprint(config: ModalUVConfig, repo_root: Path) -> str:
    """Compute the expected deployment fingerprint from local config."""
    template = load_deployment_template()
    parameters = deployment_parameters(config)
    return deployment_fingerprint(template, parameters, repo_root)


def _ensure_deployment_with_notice(
    config: ModalUVConfig, repo_root: Path, *, verbose: bool = False
) -> None:
    """Check deployment before spawning daemon. Print notice and deploy if needed."""
    template = load_deployment_template()
    parameters = deployment_parameters(config)
    expected_fp = deployment_fingerprint(template, parameters, repo_root)
    rendered = render_deployment(template, parameters, expected_fp)
    deployment_path = write_deployment_artifact(repo_root, rendered)

    needs_deploy = False
    remote_fp: str = ""
    try:
        remote_fp = query_deployed_fingerprint(config.app_name)
    except (DeploymentMissing, DeploymentBroken):
        needs_deploy = True
    except Exception:
        needs_deploy = True

    if not needs_deploy and remote_fp == expected_fp:
        return

    if needs_deploy:
        typer.echo("[modal-uv] Deploying app to Modal...", err=True)
    else:
        typer.echo("[modal-uv] Redeploying app (deployment changed)...", err=True)
        typer.echo("[modal-uv] Killing stale containers...", err=True)
        _kill_app_containers(config.app_name)

    deploy_generated_artifact(deployment_path, verbose=verbose)
    _wait_for_deployment_ready(config.app_name, expected_fp)


def _kill_app_containers(app_name: str) -> None:
    """Stop all running containers for an app to flush stale versions."""
    try:
        app_result = subprocess.run(
            [sys.executable, "-m", "modal", "app", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if app_result.returncode != 0:
            return
        apps = json.loads(app_result.stdout)
        app_id = next((a.get("App ID") for a in apps if a.get("Description") == app_name), None)
        if app_id is None:
            return

        ctr_result = subprocess.run(
            [sys.executable, "-m", "modal", "container", "list", "--app-id", app_id, "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if ctr_result.returncode != 0:
            return
        containers = json.loads(ctr_result.stdout)
        for ctr in containers:
            ctr_id = ctr.get("Container ID")
            if ctr_id:
                subprocess.run(
                    [sys.executable, "-m", "modal", "container", "stop", "-y", ctr_id],
                    capture_output=True,
                    timeout=15,
                )
    except Exception:
        pass


def _wait_for_deployment_ready(
    app_name: str, expected_fp: str, max_retries: int = 36, interval: float = 10.0
) -> None:
    """Poll the deployed fingerprint until it responds with the expected value.

    After a redeploy, Modal may keep old containers alive for up to
    scaledown_window (300s). Queries during that window can hit stale
    containers returning the old fingerprint. We poll until the new
    container is consistently serving.
    """
    typer.echo("[modal-uv] Waiting for deployment to become ready...", err=True)
    for attempt in range(1, max_retries + 1):
        try:
            remote_fp = query_deployed_fingerprint(app_name)
            if remote_fp == expected_fp:
                typer.echo(f"[modal-uv] Deployment ready (attempt {attempt}).", err=True)
                return
            typer.echo(
                f"[modal-uv] Stale container still draining "
                f"(attempt {attempt}/{max_retries}), waiting...",
                err=True,
            )
        except (DeploymentMissing, DeploymentBroken):
            typer.echo(
                f"[modal-uv] Container not ready yet (attempt {attempt}/{max_retries})...",
                err=True,
            )
        except Exception:
            typer.echo(
                f"[modal-uv] Query failed (attempt {attempt}/{max_retries}), retrying...",
                err=True,
            )
        time.sleep(interval)
    typer.echo(
        f"[modal-uv] Deployment not ready after {max_retries} attempts, proceeding anyway.",
        err=True,
    )


def _sync_and_spawn(
    project: ProjectContext,
    manifest: list,
    uv_args: list[str],
    expected_fp: str,
    *,
    _restart_attempted: bool,
) -> str:
    """Connect to daemon, plan sync, spawn run. Handles restart_needed."""
    client = ensure_daemon(project.config_path, project.repo_root)
    try:
        resp = send_request(
            client,
            "/plan_sync",
            {
                "manifest": [vars(m) for m in manifest],
                "expected_fingerprint": expected_fp,
            },
        )

        if resp["status"] == "restart_needed":
            client.close()
            if _restart_attempted:
                raise RuntimeError("daemon still reports restart_needed after restart")
            typer.echo("[modal-uv] deployment changed, restarting daemon...", err=True)
            stop_daemon(project.repo_root)
            return _sync_and_spawn(project, manifest, uv_args, expected_fp, _restart_attempted=True)

        if resp["status"] == "error":
            raise RuntimeError(resp["message"])
        missing_paths = resp["result"]

        resp = send_request(
            client,
            "/spawn",
            {
                "manifest": [vars(m) for m in manifest],
                "missing_paths": missing_paths,
                "args": uv_args,
            },
        )
        if resp["status"] == "error":
            raise RuntimeError(resp["message"])
        return resp["execution_id"]
    finally:
        client.close()
