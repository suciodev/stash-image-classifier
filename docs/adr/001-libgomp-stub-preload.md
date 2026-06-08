# ADR-001: Switch dev container base image from Alpine to Debian (python:3.12-slim)

**Status:** Superseded  
**Date:** 2026-06-06 (updated)  
**Original decision:** Replace torch's bundled libgomp with Alpine's musl-native version

## Context

The dev Stash container originally used `stashapp/stash:v0.31.1` (Alpine/musl) as its base image. PyTorch and ultralytics ship manylinux (glibc) wheels. On Alpine/musl this caused a cascade of compatibility failures:

1. **libgomp missing symbols** — torch's bundled `libgomp-*.so.1` references `pthread_attr_setaffinity_np`, `__strdup`, and other glibc extensions absent from musl. Fix: swap libgomp with Alpine's musl-native version.
2. **`__res_init` missing** — `libtorch_cpu.so` calls `__res_init` (glibc DNS init), absent from musl. Fix: compile an LD_PRELOAD stub.
3. **`.gnu.so` extension ignored** — musl Python's `EXTENSION_SUFFIXES` excludes `*-linux-gnu.so`. Torch ships `_C.cpython-312-x86_64-linux-gnu.so`; Python falls through to a namespace stub dir. Fix: symlink every `*-linux-gnu.so` to `*-linux-musl.so`.

Each layer required a separate workaround, and new layers could appear with any PyTorch upgrade. This is whack-a-mole against a bounded-but-unknown number of glibc symbols.

## Decision

Rebase the dev image on `python:3.12-slim` (Debian/glibc) and download the official `stash-linux` binary from GitHub releases. The binary has **no `DT_NEEDED` entries** (verified via ELF program header inspection): it is statically linked and runs on any x86-64 Linux kernel regardless of libc.

This eliminates the entire compatibility problem class:

| Patch removed | Why no longer needed |
|---|---|
| `apk add gcompat` | glibc is native on Debian |
| libgomp swap | torch's bundled libgomp targets glibc — it just works |
| fake opencv dist-infos | glibc opencv wheels install from PyPI normally |
| `__res_init` LD_PRELOAD stub | musl-only issue; glibc has `__res_init` |
| `.gnu.so` → `.musl.so` symlinks | Python on glibc accepts `-linux-gnu.so` natively |

The Dockerfile went from ~87 lines with multiple workaround layers to ~35 lines of straightforward installs.

## Alternatives considered

**Continue musl patching**: Had already surfaced three distinct incompatibility layers. No upper bound on future layers; risk of silent glibc-specific behavior at inference time even if `import torch` succeeds.

**Alpine base + static torch build**: No static PyPI wheels for torch; building from source is hours of compile time and not viable in a dev image.

**Sidecar inference container (glibc)**: Stash invokes plugins as subprocesses within its own container, so a separate inference container would require refactoring the plugin into an HTTP client — more work than a base-image swap.

## Consequences

- Dev image no longer matches the production Stash container (Alpine). The stash binary and Python runtime differ, but plugin code (`main.py`, `src/`) is platform-agnostic Python and runs identically.
- torch, ultralytics, and opencv now install as standard PyPI wheels with no modifications — upgrades are straightforward.
- Image size is comparable: Debian slim + pip installs vs Alpine + gcompat + workarounds.
