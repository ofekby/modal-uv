"""Deployment artifact and fingerprint helpers for modal-uv."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from modal_uv.config import ModalUVConfig
from modal_uv.paths import repo_state_dir

DEPLOYMENT_TEMPLATE = '''\
"""Generated modal-uv deployment. Do not edit by hand."""

from __future__ import annotations

from modal_uv.app import create_app

DEPLOYMENT_FINGERPRINT = {fingerprint!r}

app = create_app(
    app_name={app_name!r},
    gpu={gpu!r},
    volume_name={volume_name!r},
    volume_mount_path={volume_mount_path!r},
    commit_interval_seconds={commit_interval_seconds!r},
    work_dir={work_dir!r},
    image_base={image_base!r},
)


@app.function()
def deployment_fingerprint() -> str:
    return DEPLOYMENT_FINGERPRINT
'''


class DeploymentMissing(RuntimeError):
    """Raised when the deployed Modal app or fingerprint function is missing."""


def deployment_parameters(config: ModalUVConfig) -> dict[str, Any]:
    """Return config values that affect the Modal deployment shape."""
    return {
        "app_name": config.app_name,
        "gpu": config.gpu,
        "work_dir": config.work_dir.as_posix(),
        "volume": {
            "name": config.volume.name,
            "mount_path": config.volume.mount_path.as_posix(),
            "commit_interval_seconds": config.volume.commit_interval_seconds,
        },
        "image": {
            "python_version": config.image.python_version,
            "base_image": config.image.base_image,
        },
    }


def pyproject_sha256(repo_root: Path) -> str | None:
    """Return the repo pyproject.toml SHA256, if present."""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return None
    return hashlib.sha256(pyproject.read_bytes()).hexdigest()


def deployment_tool_versions() -> dict[str, str]:
    """Return local tool versions that should force a redeploy when changed."""
    return {
        "modal_uv": _package_version("modal-uv"),
        "uv": _uv_version(),
        "modal": _package_version("modal"),
    }


def deployment_fingerprint(
    template_text: str,
    parameters: dict[str, Any],
    repo_root: Path,
    *,
    tool_versions: Mapping[str, str] | None = None,
) -> str:
    """Return a deterministic fingerprint for the desired deployment."""
    payload = {
        "template": template_text,
        "parameters": parameters,
        "pyproject_sha256": pyproject_sha256(repo_root),
        "tool_versions": dict(tool_versions or deployment_tool_versions()),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _uv_version() -> str:
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unavailable"
    if result.returncode != 0:
        return "unavailable"
    return result.stdout.strip() or result.stderr.strip() or "unavailable"


def load_deployment_template() -> str:
    """Return the package-owned deployment template text."""
    return DEPLOYMENT_TEMPLATE


def render_deployment(template_text: str, parameters: dict[str, Any], fingerprint: str) -> str:
    """Render a generated deployment.py artifact."""
    volume = parameters["volume"]
    image = parameters["image"]
    return template_text.format(
        fingerprint=fingerprint,
        app_name=parameters["app_name"],
        gpu=parameters["gpu"],
        volume_name=volume["name"],
        volume_mount_path=volume["mount_path"],
        commit_interval_seconds=volume["commit_interval_seconds"],
        work_dir=parameters["work_dir"],
        image_base=image["base_image"],
    )


def write_deployment_artifact(repo_root: Path, rendered_text: str) -> Path:
    """Write the repo-local generated deployment artifact."""
    destination = repo_state_dir(repo_root) / "deployment.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_text(encoding="utf-8") != rendered_text:
        destination.write_text(rendered_text, encoding="utf-8")
    return destination


def ensure_deployment_current(
    config: ModalUVConfig,
    repo_root: Path,
    *,
    query_remote_fingerprint: Callable[[str], str] | None = None,
    deploy_artifact: Callable[[Path], None] | None = None,
) -> str:
    """Ensure the Modal deployment matches local config and return its fingerprint."""
    template = load_deployment_template()
    parameters = deployment_parameters(config)
    fingerprint = deployment_fingerprint(template, parameters, repo_root)
    rendered = render_deployment(template, parameters, fingerprint)
    deployment_path = write_deployment_artifact(repo_root, rendered)

    query = query_remote_fingerprint or query_deployed_fingerprint
    deploy = deploy_artifact or deploy_generated_artifact

    try:
        remote_fingerprint = query(config.app_name)
    except DeploymentMissing:
        deploy(deployment_path)
        return fingerprint

    if remote_fingerprint != fingerprint:
        deploy(deployment_path)

    return fingerprint


def query_deployed_fingerprint(app_name: str) -> str:
    """Query the deployed Modal app fingerprint."""
    import modal

    try:
        return str(modal.Function.from_name(app_name, "deployment_fingerprint").remote())
    except modal.exception.NotFoundError as exc:
        raise DeploymentMissing(str(exc)) from exc


def deploy_generated_artifact(deployment_path: Path) -> None:
    """Deploy the generated Modal app artifact."""
    subprocess.run([sys.executable, "-m", "modal", "deploy", str(deployment_path)], check=True)
