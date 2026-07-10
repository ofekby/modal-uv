"""Modal app definition for modal-uv."""

from __future__ import annotations

import os
import subprocess
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import modal

from modal_uv.sync import (
    STATE_FILE_NAME,
    FilePayload,
    FileState,
    plan_sync,
    save_state_csv,
    uv_run_command,
    uv_run_env,
)


def _modal_uv_version() -> str:
    try:
        return version("modal-uv")
    except PackageNotFoundError:
        return os.environ["MODAL_UV_VERSION"]


_INFRA_ENV = {
    "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin",
    "MODAL_UV_VERSION": _modal_uv_version(),
    "UV_LINK_MODE": "copy",
    "UV_PROJECT_ENVIRONMENT": "/usr/local",
}


def create_app(
    app_name: str,
    gpu: str | None,
    cpu: float | None,
    memory: int | None,
    volumes: list[dict[str, Any]],
    env: dict[str, str],
    timeout_seconds: int,
    scaledown_window_seconds: int,
    runtime_exec: str | None,
    work_dir: str,
    image_base: str,
    add_python_version: str | None,
    fingerprint: str,
) -> modal.App:
    """Create a Modal app from config."""
    app = modal.App(name=app_name)

    modal_volumes: dict[str, modal.Volume] = {}
    for vol in volumes:
        mv = modal.Volume.from_name(vol["name"], create_if_missing=True)
        modal_volumes[vol["mount_path"]] = mv

    merged_env = {**_INFRA_ENV, **env}

    image_kwargs: dict[str, Any] = {}
    if add_python_version and add_python_version != "inherit":
        image_kwargs["add_python"] = add_python_version

    image = (
        modal.Image.from_registry(image_base, **image_kwargs)
        .apt_install("curl")
        .run_commands("curl -LsSf https://astral.sh/uv/install.sh | sh")
        .pip_install("pathspec")
        .env(merged_env)
        .add_local_python_source("modal_uv")
    )

    @app.function(image=image, serialized=True, name="deployment_fingerprint")
    def _deployment_fingerprint() -> str:
        return fingerprint

    commit_specs: list[tuple[modal.Volume, int]] = [
        (mv, vol["commit_interval_seconds"])
        for vol, mv in zip(volumes, modal_volumes.values(), strict=True)
    ]

    cls_options: dict[str, Any] = {
        "scaledown_window": scaledown_window_seconds,
        "timeout": timeout_seconds,
        "max_containers": 1,
        "image": image,
        "serialized": True,
    }
    if modal_volumes:
        cls_options["volumes"] = modal_volumes
    if gpu is not None:
        cls_options["gpu"] = gpu
    if cpu is not None:
        cls_options["cpu"] = cpu
    if memory is not None:
        cls_options["memory"] = memory

    @app.cls(**cls_options)
    @modal.concurrent(max_inputs=1)
    class Worker:
        """Sync files and execute commands on Modal."""

        @modal.method()
        def plan_sync(self, manifest: list[FileState]) -> list[str]:
            """Delete extra remote files and return missing/stale paths."""
            return plan_sync(Path(work_dir), manifest)

        @modal.method()
        def sync_and_run(
            self,
            manifest: list[FileState],
            files: list[FilePayload],
            args: list[str],
            mode: str = "run",
        ) -> int:
            """Upload missing files and execute a command."""
            os.makedirs(work_dir, exist_ok=True)
            for file in files:
                file.write_to(Path(work_dir))
            save_state_csv(Path(work_dir) / STATE_FILE_NAME, manifest)

            if mode == "run":
                command = uv_run_command(args)
            elif mode == "exec":
                if not args or not args[0].strip():
                    raise ValueError("exec command is required")
                shell = runtime_exec or os.environ.get("SHELL") or "/bin/sh"
                command = [shell, "-c", args[0]]
            else:
                raise ValueError(f"unknown execution mode: {mode}")

            stop_event = threading.Event()
            threads: list[threading.Thread] = []

            for vol_obj, interval in commit_specs:

                def make_commit_thread(v: modal.Volume, iv: int) -> threading.Thread:
                    def loop() -> None:
                        while not stop_event.wait(iv):
                            try:
                                v.commit()
                            except Exception as exc:
                                print(f"[modal-uv] periodic commit failed: {exc}", flush=True)

                    return threading.Thread(target=loop, daemon=True)

                t = make_commit_thread(vol_obj, interval)
                t.start()
                threads.append(t)

            result = subprocess.run(
                command,
                cwd=work_dir,
                env=uv_run_env(Path(work_dir)),
            )
            stop_event.set()
            for t in threads:
                t.join(timeout=10)

            for vol_obj, _ in commit_specs:
                vol_obj.commit()
            return result.returncode

    return app
