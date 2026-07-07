# Modal-UV Preload Imports Design

**Date:** 2026-06-06
**Status:** Approved
**Scope:** Add configured image-environment import preloading for warm `modal-uv py` executions.

## Problem

`modal-uv py` reuses imports after the first warm execution, but the first Python execution still pays the cost of importing heavy image dependencies such as PyTorch and initializing related libraries. We want the warm worker to preload selected third-party imports before user code runs, while ensuring those imports come only from the container image environment and not from synced local source files.

## Goals

- Add static preload import configuration to `modal-uv.yaml`.
- Preload configured imports once per warm Modal container.
- Resolve preload imports only from the image/system environment.
- Keep preloaded modules cached in `sys.modules` for later `modal-uv py` executions.
- Print per-import timing logs.
- Fail loudly if a configured preload import fails.

## Non-Goals

- No per-command preload flags.
- No runtime dependency installation.
- No local source preloading.
- No automatic reload of preloaded modules after source sync.

## Configuration

Add optional config:

```yaml
preload:
  imports:
    - torch
    - numpy
```

`preload.imports` defaults to an empty tuple.

## Worker Behavior

The deployed Modal worker will preload configured imports during warm container initialization, before any command execution.

For each import name:

1. Temporarily remove `/tmp/work` and `/tmp/work/src` from `sys.path`.
2. Call `importlib.import_module(name)`.
3. Restore `sys.path`.
4. Print timing:

```text
[modal-uv] preloaded torch: 1.934s
```

If an import fails, the exception propagates. This makes a bad preload configuration visible immediately instead of falling back to slower execution.

## Local Source Isolation

Preload must not resolve from synced local source files. Defense-in-depth:

- Run preload before sync paths are added for `modal-uv py`.
- Explicitly remove `/tmp/work` and `/tmp/work/src` from `sys.path` while preloading.
- Do not call `importlib.invalidate_caches()` with local sync paths active during preload.

`modal-uv py` may later add `/tmp/work/src` and `/tmp/work` to `sys.path` for user code execution, but preloaded modules are already resolved from the image environment.

## Testing Strategy

- Unit-test config parsing for `preload.imports`.
- Unit-test default preload config is empty.
- Unit-test preload helper imports configured module names.
- Unit-test preload helper temporarily excludes local work paths from `sys.path`.
- Unit-test failed preload imports propagate.
- Smoke-test deployed `modal-uv py -- -m lab` with `torch` preloaded and confirm first-run Python execution no longer pays the full import cost.
