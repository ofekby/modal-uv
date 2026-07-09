"""Run uv commands on Modal.com with GPU and persistent volumes."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version


def _version() -> str:
    try:
        return version("modal-uv")
    except PackageNotFoundError:
        return os.environ["MODAL_UV_VERSION"]


__version__ = _version()
