"""Modal app definition for modal-uv."""

from __future__ import annotations

import os
import subprocess
import threading
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

COMMIT_INTERVAL_SECONDS = 30


def create_app(
    app_name: str,
    gpu: str | None,
    volume_name: str,
    volume_mount_path: str,
    work_dir: str,
    image_base: str,
    commit_interval_seconds: int = COMMIT_INTERVAL_SECONDS,
) -> modal.App:
    """Create a Modal app from config."""
    app = modal.App(name=app_name)

    modal_volume = modal.Volume.from_name(
        volume_name,
        create_if_missing=True,
    )

    image = (
        modal.Image.from_registry(image_base)
        .apt_install("curl")
        .run_commands("curl -LsSf https://astral.sh/uv/install.sh | sh")
        .env(
            {
                "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin",
                "HF_HUB_CACHE": f"{volume_mount_path}/huggingface/hub",
                "HF_HOME": f"{volume_mount_path}/huggingface",
                "HF_XET_HIGH_PERFORMANCE": "1",
                "UV_LINK_MODE": "copy",
                "UV_PROJECT_ENVIRONMENT": "/usr/local",
            }
        )
        .add_local_python_source("modal_uv")
    )

    cls_options: dict[str, Any] = {
        "volumes": {volume_mount_path: modal_volume},
        "scaledown_window": 300,
        "timeout": 7200,
        "max_containers": 1,
        "image": image,
        "serialized": True,
    }
    if gpu is not None:
        cls_options["gpu"] = gpu

    @app.cls(**cls_options)
    @modal.concurrent(max_inputs=1)
    class Worker:
        """Sync files and execute uv commands on Modal."""

        @modal.method()
        def plan_sync(self, manifest: list[FileState]) -> list[str]:
            """Delete extra remote files and return missing/stale paths."""
            return plan_sync(Path(work_dir), manifest)

        @modal.method()
        def sync_and_run(
            self, manifest: list[FileState], files: list[FilePayload], args: list[str]
        ) -> int:
            """Upload missing files and execute uv run <args>."""
            os.makedirs(work_dir, exist_ok=True)
            for file in files:
                file.write_to(Path(work_dir))
            save_state_csv(Path(work_dir) / STATE_FILE_NAME, manifest)

            stop_event = threading.Event()

            def periodic_volume_commit() -> None:
                while not stop_event.wait(commit_interval_seconds):
                    try:
                        modal_volume.commit()
                    except Exception as exc:
                        print(f"[modal-uv] periodic commit failed: {exc}", flush=True)

            commit_thread = threading.Thread(target=periodic_volume_commit, daemon=True)
            commit_thread.start()
            result = subprocess.run(
                uv_run_command(args),
                cwd=work_dir,
                env=uv_run_env(Path(work_dir)),
            )
            stop_event.set()
            commit_thread.join(timeout=10)

            modal_volume.commit()
            return result.returncode

    return app
