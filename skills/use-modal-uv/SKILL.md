---
name: use-modal-uv
description: Run uv commands on Modal.com with GPU, direct file sync, lazy app deployment, async execution IDs, logs, abort, and persistent volumes.
---

# Modal-UV

Run `uv` commands on Modal.com with GPU acceleration, direct file sync, lazy Modal app deployment, async execution IDs, logs, abort, and a persistent Modal volume for outputs.

## Quick Start

```bash
# Run a script on Modal with GPU
modal-uv run -- python script.py

# Run a module on Modal with GPU
modal-uv run -- python -m mymodule

# Run tests on Modal
modal-uv run -- pytest tests/ -v

# Run shell-style commands on Modal
modal-uv exec -- nvidia-smi
modal-uv exec -- 'ls -la && pwd'
# Quote commands containing shell metacharacters so your local shell does not consume them.
# Without quotes, `&&`, `|`, `>`, `*`, etc. are interpreted locally before modal-uv sees them.

# Tail or abort a spawned execution
modal-uv logs fc-...
modal-uv abort fc-...

# Open Modal's native interactive shell
modal-uv modal -- shell

# Check app status
modal-uv status
```

## Architecture

```text
Local Repo -> daemon -> lazy deploy/check -> plan_sync.remote() -> sync_and_run.spawn()
```

- `modal-uv` discovers the repo by walking up to `modal-uv.yaml`.
- Repo-local generated state lives under `.modal-uv/`, which is gitignored.
- Deployment (image build, fingerprint check) happens directly in the CLI before connecting to the daemon. The daemon handles file sync and command execution on the warm container.
- `modal-uv run` and `modal-uv exec` print a Modal function call ID immediately and return.
- Subprocess stdout/stderr go to Modal logs.
- Modal authentication remains Modal's user-global authentication.

See [Sync vs Deployment](#sync-vs-deployment-when-does-each-happen) for details on when code is synced vs when the app is redeployed.

## Configuration

### modal-uv.yaml

```yaml
app_name: "my-project"
work_dir: "/tmp/work"

volumes:
  - name: "modal-uv-cache"
    mount_path: "/mnt/volume"
    commit_interval_seconds: 30

env: {}

runtime:
  gpu: "T4"
  cpu: 2
  memory: 4096
  scaledown_window_seconds: 300

image:
  base_image: "python:3.12-slim"
  # add_python_version: null  # Only for non-Python base images (see below)

sync:
  ignore:
    - "data/**"
    - "*.ckpt"
```

#### Non-Python base images

For base images that do not include Python (e.g., `nvidia/cuda:12.4.0-devel-ubuntu22.04`), `add_python_version` is required:

```yaml
image:
  base_image: "nvidia/cuda:12.4.0-devel-ubuntu22.04"
  add_python_version: "3.12"    # Modal adds a standalone Python of this version
```

For custom images that already include Python but are not recognized (e.g., a private conda image), use `"inherit"` to skip adding Python:

```yaml
image:
  base_image: "my-registry/custom:latest"
  add_python_version: "inherit"
```

Known Python images (`python:*`, `pytorch/pytorch:*`, `continuumio/miniconda3:*`, `continuumio/anaconda3:*`) do not need `add_python_version`. Setting it on those images raises a validation error.

#### Dependency isolation

Project dependencies installed by `uv run` are isolated in a virtual environment inside the work directory (`work_dir/.venv`). This prevents project `uv sync` from removing or conflicting with the container's infrastructure packages.

## Workflow

### 1. Run Scripts on Modal

```bash
modal-uv run -- python script.py
modal-uv run -- pytest tests/ -v
modal-uv run -- python -m lab
```

Add `--verbose` (or `-v`) to `run` or `exec` to stream deployment output to the terminal, useful when diagnosing slow image builds or redeploys:

```bash
modal-uv run --verbose -- pytest
modal-uv exec --verbose -- nvidia-smi
```

### 2. Inspect Execution

```bash
modal-uv logs fc-...
modal-uv abort fc-...
```

### 3. Run Shell Commands

```bash
modal-uv exec -- nvidia-smi
modal-uv exec -- 'ls -la && pwd'
```

Quote shell-style command strings that contain local shell metacharacters such as `&&`, `|`, `>`, `<`, `*`, or variable expansions. For example, use `modal-uv exec -- 'python --version && nproc'`; otherwise your local shell may run part of the command locally before `modal-uv` sees it.

### 4. Inspect Generated State

```bash
ls -la .modal-uv/
```

## Sync vs Deployment: When Does Each Happen?

modal-uv separates two runtime concerns: **fast code sync** and **app deployment**. Understanding the difference avoids unnecessary redeploys and keeps iteration fast.

### Fast Code Sync (every `modal-uv run` or `modal-uv exec`)

When you run `modal-uv run -- ...` or `modal-uv exec -- ...`, the daemon:

1. Scans local files (respecting built-in ignores + `sync.ignore`).
2. Sends a manifest of `path,size,mtime_ns,mode` (including file permissions) to the warm Modal container.
3. The container compares against `.last-received-files-state.csv` and reports which files are missing or stale.
4. Only those files are uploaded.
5. `run` executes `uv run --link-mode copy ...`; `exec` executes the resolved remote shell directly.

This is fast (seconds), incremental, and happens on every run. It covers:

- Editing Python source files
- Adding/removing files in the repo
- Changing config values that only affect local file selection (e.g. `sync.ignore`)

No redeploy is needed for any of these. The warm container's filesystem is the sync target, not the Modal image.

### App Deployment (lazy, only when fingerprint changes)

The daemon deploys or redeploys the Modal app only when a **deployment fingerprint** changes. The fingerprint is a SHA256 hash of:

- The unrendered deployment template (shipped with the `modal-uv` package)
- Modal-relevant config values from `modal-uv.yaml`: `app_name`, `work_dir`, `volumes`, `env`, `runtime`, `image.base_image`, `image.add_python_version`
- The SHA256 of the repo root `pyproject.toml` (if present)
- Local tool versions (`modal-uv`, `uv`, `modal`)

On daemon startup, it queries the deployed app's fingerprint. If it matches, the existing deployment is reused. If it differs or the app is missing, it generates `.modal-uv/deployment.py` and runs `modal deploy`.

**What triggers a redeploy:**

- Changing `runtime.gpu` from `T4` to `A100`
- Changing `app_name`, `work_dir`, `volumes`, `env`, or `runtime`
- Changing `image.add_python_version` or `image.base_image`
- Updating dependencies in `pyproject.toml` (its SHA256 changes)
- Upgrading `modal-uv` itself (the deployment template may change)

**What does NOT trigger a redeploy:**

- Editing Python source files (handled by sync)
- Changing `sync.ignore` (affects local file selection only)
- Adding/removing non-`pyproject.toml` files

### Why This Split?

Redeploying a Modal app is slow (image rebuild, container restart). Code sync is fast (file upload to a warm container). By fingerprinting only deployment-shape inputs, modal-uv avoids redeploys for ordinary code changes while still catching dependency or infrastructure changes automatically.

## Troubleshooting

### View Logs

```bash
modal-uv modal -- app logs my-project
```

### Check Volume

```bash
modal-uv modal -- volume ls modal-uv-cache
```

### Deployment Issues

modal-uv is designed to recover automatically. If the deployment is stale or missing, the next `modal-uv run` or `modal-uv exec` detects it via fingerprint comparison and redeploys. Avoid manually stopping or redeploying the app — just run your command again:

```bash
modal-uv run -- pytest
```

If the warm container's file state is corrupted, `modal-uv run` or `modal-uv exec` will detect missing/stale files and re-upload them automatically on the next run.
