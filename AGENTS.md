# AGENTS.md

## Purpose

`modal-uv` exists to let coding agents and developers run ordinary `uv` workflows on Modal without turning every project into a Modal application.

The tool is for moments when local development is convenient, but local hardware is not enough: GPU tests, model experiments, long-running jobs, or artifact-producing scripts should be runnable from the same repo, with the same `uv` command shape, and without manual deployment ceremony.

## Philosophy

- Preserve the local development loop. A project should stay a normal Python project first.
- Make remote execution feel boring. Running on Modal should be a transport choice, not a rewrite.
- Prefer explicit project configuration over hidden global state.
- Keep generated/runtime state out of the source tree's meaningful files.
- Optimize for coding agents as first-class users: commands should be discoverable, repeatable, and safe to diagnose.
- Separate fast iteration from deployment. Source changes should sync directly; deployment should happen only when the runtime shape changes.
- Treat Modal authentication as user-level infrastructure, not repo-local project state.

## Problem It Solves

Without `modal-uv`, using cloud GPUs from an existing repo usually means adding Modal-specific entrypoints, managing deploy commands manually, copying files around, or teaching each coding agent a custom workflow.

`modal-uv` aims to provide one small bridge: keep the repo local, run the command remotely, sync only what changed, persist useful outputs in a Modal Volume, and return enough execution information for agents and humans to inspect logs or stop work.
