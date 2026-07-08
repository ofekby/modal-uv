"""Configuration loading for modal-uv."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource


class ConfigError(ValueError):
    """Raised when modal-uv configuration is missing or invalid."""


@dataclass(frozen=True)
class ProjectContext:
    """Resolved repo root and config path for a modal-uv project."""

    repo_root: Path
    config_path: Path


@dataclass(frozen=True)
class VolumeConfig:
    """Modal volume configuration."""

    name: str
    mount_path: Path
    commit_interval_seconds: int


@dataclass(frozen=True)
class ImageConfig:
    """Container image configuration."""

    python_version: str
    base_image: str


@dataclass(frozen=True)
class SyncConfig:
    """Local sync configuration."""

    ignore: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeConfig:
    """Modal runtime behavior configuration."""

    scaledown_window_seconds: int


@dataclass(frozen=True)
class ModalUVConfig:
    """Complete modal-uv configuration."""

    app_name: str
    gpu: str | None
    work_dir: Path
    volumes: tuple[VolumeConfig, ...]
    env: tuple[tuple[str, str], ...]
    runtime: RuntimeConfig
    image: ImageConfig
    sync: SyncConfig


ALLOWED_GPUS = frozenset(
    {
        "T4",
        "A10G",
        "A10",
        "A100",
        "A100-40GB",
        "A100-80GB",
        "L4",
        "L40S",
        "H100",
        "H200",
        "B200",
        "B200+",
        "RTX-PRO-6000",
    }
)

_DEFAULT_VOLUME_MOUNT = Path("/root/.cache")
_DEFAULT_WORK_DIR = Path("/root/work")
_DEFAULT_PYTHON_VERSION = "3.12"
_DEFAULT_BASE_IMAGE = "python:3.12-slim"
_DEFAULT_COMMIT_INTERVAL_SECONDS = 30
_DEFAULT_SCALEDOWN_WINDOW_SECONDS = 300


class _RawVolume(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    mount_path: Path = _DEFAULT_VOLUME_MOUNT
    commit_interval_seconds: int = _DEFAULT_COMMIT_INTERVAL_SECONDS

    @field_validator("commit_interval_seconds")
    @classmethod
    def validate_commit_interval_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("commit_interval_seconds must be greater than 0")
        return value


class _RawImage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    python_version: str = _DEFAULT_PYTHON_VERSION
    base_image: str = _DEFAULT_BASE_IMAGE


class _RawSync(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ignore: list[str] = Field(default_factory=list)


class _RawRuntime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scaledown_window_seconds: int = _DEFAULT_SCALEDOWN_WINDOW_SECONDS

    @field_validator("scaledown_window_seconds")
    @classmethod
    def validate_scaledown_window_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("scaledown_window_seconds must be greater than 0")
        return value


class _RawSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = ""
    gpu: str | None = None
    work_dir: Path = _DEFAULT_WORK_DIR
    volumes: list[_RawVolume] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    runtime: _RawRuntime = Field(default_factory=_RawRuntime)
    image: _RawImage = Field(default_factory=_RawImage)
    sync: _RawSync = Field(default_factory=_RawSync)

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("app_name must be a non-empty string")
        return value.strip()

    @field_validator("gpu")
    @classmethod
    def validate_gpu(cls, value: str | None) -> str | None:
        if value is None:
            return None
        upper = value.strip().upper()
        if upper in {"", "NONE", "CPU"}:
            return None
        if upper not in ALLOWED_GPUS:
            raise ValueError(f"gpu must be one of {sorted(ALLOWED_GPUS)}, got {value!r}")
        return upper

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=_yaml_path)
        return (yaml_source, init_settings)


_yaml_path: Path = Path("modal-uv.yaml")


def resolve_project(config_path: Path | None = None, start: Path | None = None) -> ProjectContext:
    """Resolve the modal-uv repo root and config path."""
    if config_path is not None:
        resolved_config = config_path.expanduser().resolve()
        return ProjectContext(repo_root=resolved_config.parent, config_path=resolved_config)

    current = (start or Path.cwd()).resolve()
    candidates = (current, *current.parents)
    for directory in candidates:
        candidate = directory / "modal-uv.yaml"
        if candidate.exists():
            return ProjectContext(repo_root=directory, config_path=candidate)

    raise ConfigError("modal-uv.yaml not found in current directory or any parent")


def load_config(config_path: Path | None = None) -> ModalUVConfig:
    """Load and validate modal-uv configuration from YAML."""
    global _yaml_path
    _yaml_path = resolve_project(config_path).config_path

    if not _yaml_path.exists():
        raise ConfigError(f"config file not found: {_yaml_path}")

    try:
        settings = _RawSettings()
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc
    except Exception as exc:
        raise ConfigError(f"failed to load config from {_yaml_path}: {exc}") from exc

    if not settings.app_name.strip():
        raise ConfigError("app_name is required")

    volumes: list[VolumeConfig] = []
    for raw_vol in settings.volumes:
        if not raw_vol.name.strip():
            raise ConfigError("each volume must have a name")
        volumes.append(
            VolumeConfig(
                name=raw_vol.name.strip(),
                mount_path=raw_vol.mount_path,
                commit_interval_seconds=raw_vol.commit_interval_seconds,
            )
        )

    return ModalUVConfig(
        app_name=settings.app_name,
        gpu=settings.gpu,
        work_dir=settings.work_dir,
        volumes=tuple(volumes),
        env=tuple(settings.env.items()),
        runtime=RuntimeConfig(
            scaledown_window_seconds=settings.runtime.scaledown_window_seconds,
        ),
        image=ImageConfig(
            python_version=settings.image.python_version,
            base_image=settings.image.base_image,
        ),
        sync=SyncConfig(
            ignore=tuple(item.strip() for item in settings.sync.ignore if item.strip())
        ),
    )


def _format_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid modal-uv configuration"

    first = errors[0]
    field = str(first.get("loc", ["configuration"])[0])
    message = first.get("msg", "invalid value")
    return f"invalid {field}: {message}"
