# Modal-UV Global CLI Design

**Date:** 2026-07-06

**Scope:** Adapt `modal-uv` from a repo-embedded helper into a globally installed CLI that owns repo discovery, repo-local generated state, sync ignores, and lazy Modal app deployment.

## Goals

- Allow `modal-uv` to be installed globally, eventually with `pip install modal-uv`.
- Let users run `modal-uv` from any subdirectory inside a configured repo.
- Keep repo-specific configuration in `modal-uv.yaml`.
- Keep generated/runtime repo state under `.modal-uv/`.
- Keep Modal authentication in Modal's normal user-global auth locations.
- Make the detached daemon responsible for all Modal SDK interactions.
- Lazily deploy or redeploy the Modal app when the configured deployment is missing or stale.
- Remove `modal-uv py`, in-process Python execution, and preload behavior for now.

## Non-Goals

- No migration support for `.s3-sync-ignore`; `sync.ignore` replaces it.
- No in-process Python execution mode.
- No preload configuration.
- No Modal auth management, token copying, or repo-local auth files.
- No redeploy on ordinary source file changes; source changes continue through the sync mechanism.

## Repo Discovery

When `--config` is not provided, the CLI walks upward from the current working directory until it finds `modal-uv.yaml`. The directory containing that file is the repo root.

When `--config` is provided, the config file's parent directory is the repo root.

If no config is found, commands that require a repo fail with a clear error explaining that `modal-uv.yaml` was not found in the current directory or its parents.

## Repo State Directory

The CLI creates `.modal-uv/` at the repo root on first use.

The root `.gitignore` should contain `.modal-uv/`. If `.gitignore` is missing, the CLI creates it. If `.gitignore` exists and does not already ignore `.modal-uv/`, the CLI appends that entry.

`.modal-uv/` contains generated and runtime files such as:

- `.modal-uv/deployment.py`
- `.modal-uv/daemon.pid`
- `.modal-uv/daemon.sock`
- `.modal-uv/daemon.log`

There is no `.modal-uv/.gitignore` and no `.modal-uv/.ignore`. The whole `.modal-uv/` directory is repo-local generated state.

## Sync Ignore Configuration

Custom sync ignores live only in `modal-uv.yaml`:

```yaml
sync:
  ignore:
    - "data/**"
    - "*.ckpt"
```

`sync.ignore` uses gitignore-style patterns and defaults to an empty list.

Built-in ignores still exclude local-only and generated paths, including `.git/`, `.venv/`, `node_modules/`, Python caches, `.env`, lock/cache directories, and `.modal-uv/`.

`.s3-sync-ignore` is no longer read and should not be mentioned in new docs.

## CLI Commands

The first pass keeps the main command surface small:

- `modal-uv run -- ...`: sync and run `uv run --link-mode copy ...` remotely.
- `modal-uv logs <function-call-id>`: follow logs for a spawned run.
- `modal-uv abort <function-call-id>`: cancel a spawned run.
- `modal-uv shell`: open a Modal shell using the configured volume/GPU.
- `modal-uv status`: show configured Modal app status.
- `modal-uv daemon-stop`: stop the repo-local daemon.
- `modal-uv daemon-status`: show repo-local daemon state.

`modal-uv py` is removed. The supporting daemon endpoint, Modal worker method, config fields, helper functions, docs, and tests for in-process Python execution are removed with it.

## Configuration Shape

`modal-uv.yaml` remains the repo-level source of truth:

```yaml
app_name: "my-project"
gpu: "T4"
work_dir: "/tmp/work"

volume:
  name: "modal-uv-cache"
  mount_path: "/mnt/volume"

image:
  python_version: "3.12"
  base_image: "python:3.12-slim"

sync:
  ignore:
    - "data/**"
```

`preload` is removed because it only helped `modal-uv py`. `modal-uv run` executes user code in a subprocess, so imports performed in the worker process are not reused by the subprocess.

## Lazy Deployment

The foreground CLI does local repo work only:

- Resolve repo root and config path.
- Load and validate `modal-uv.yaml`.
- Ensure `.modal-uv/` and root `.gitignore` behavior.
- Build the local sync manifest.
- Start or contact the detached daemon.

The detached daemon performs all Modal SDK interactions:

- Generate or refresh `.modal-uv/deployment.py` from a package-owned template.
- Compute the deployment fingerprint.
- Check whether the Modal app exists.
- Query the deployed app fingerprint when possible.
- Deploy when the app is missing or stale.
- Initialize `modal.Cls.from_name(app_name, "Worker")()` only after deployment is current.
- Serve `/plan_sync` and `/spawn` requests for `modal-uv run`.

This preserves user-global Modal authentication behavior because the detached daemon imports and uses Modal SDK/CLI tooling from the user's environment. `modal-uv` does not manage Modal credentials itself.

## Deployment Artifact

`.modal-uv/deployment.py` is generated from a template shipped with the `modal-uv` package. It is used locally by the daemon for Modal deployment mechanics and debugging. It is not source-of-truth and is not synced as ordinary repo payload.

Normal repo sync ignores `.modal-uv/`. If a future generated artifact must exist inside the remote work directory, it should be added through an explicit internal allowlist rather than making `.modal-uv/` generally syncable.

## Deployment Fingerprint

The daemon computes a deterministic fingerprint from:

- The unrendered deployment template contents.
- The rendered deployment parameter values derived from `modal-uv.yaml`.
- The SHA256 of the repo root `pyproject.toml` if it exists.

If `pyproject.toml` changes, the fingerprint changes and the daemon redeploys the Modal app. Ordinary source changes do not affect the deployment fingerprint because they are handled by the sync mechanism.

The deployed Modal app exposes a small method or function that returns its embedded fingerprint. The daemon uses this to decide whether the deployed app matches the local desired deployment.

## Data Flow

For `modal-uv run -- pytest`:

1. CLI discovers repo root from `modal-uv.yaml`.
2. CLI loads config and `sync.ignore`.
3. CLI ensures `.modal-uv/` exists and root `.gitignore` ignores it.
4. CLI builds a manifest of syncable files.
5. CLI starts or connects to the repo daemon via `.modal-uv/daemon.sock`.
6. Daemon lazily deploys or reuses the configured Modal app.
7. CLI asks daemon to plan remote sync.
8. CLI asks daemon to spawn the remote `uv run --link-mode copy pytest` call.
9. CLI prints the function call ID plus `logs` and `abort` hints.

## Error Handling

- Missing config: fail with a clear message naming `modal-uv.yaml` discovery behavior.
- Invalid config: fail before daemon startup when possible.
- Root `.gitignore` cannot be created or updated: fail before running remote work, because otherwise `.modal-uv/` may be accidentally tracked.
- Daemon startup failure: surface the daemon log path in `.modal-uv/daemon.log`.
- Deploy failure: propagate the Modal deployment error through the daemon response.
- Fingerprint query failure: treat as stale or missing only when the app cannot be queried because it is absent; unexpected query errors should fail loudly.

## Testing

Unit tests should cover:

- Upward config discovery from nested directories.
- `--config` override and repo root selection.
- `.modal-uv/` creation.
- Root `.gitignore` creation/update for `.modal-uv/`.
- Daemon path resolution under `.modal-uv/`.
- Config parsing for `sync.ignore`.
- Manifest ignores from built-ins plus `sync.ignore`.
- `.s3-sync-ignore` is not read.
- Removal of `modal-uv py` from CLI help.
- Removal of preload config parsing.
- Deployment fingerprint changes when template, deployment parameters, or `pyproject.toml` changes.
- Daemon deploy decision for missing, stale, and current deployments using mocked Modal interactions.

Integration-style tests can mock subprocess/Modal boundaries and verify that foreground CLI commands do not import or call Modal SDK deployment operations directly.

## Open Decisions

No open product decisions remain for this scope.
