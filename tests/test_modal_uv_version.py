"""Tests for modal-uv package version loading."""

from __future__ import annotations

import importlib
import importlib.metadata
import sys

import pytest


def test_version_falls_back_to_environment_when_distribution_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_module = sys.modules.pop("modal_uv", None)
    monkeypatch.setenv("MODAL_UV_VERSION", "9.9.9")

    def missing_version(_package_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("modal-uv")

    monkeypatch.setattr(importlib.metadata, "version", missing_version)

    try:
        module = importlib.import_module("modal_uv")
        assert module.__version__ == "9.9.9"
    finally:
        sys.modules.pop("modal_uv", None)
        if previous_module is not None:
            sys.modules["modal_uv"] = previous_module
