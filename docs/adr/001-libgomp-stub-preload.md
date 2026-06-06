# ADR-001: LD_PRELOAD stub for missing pthread_attr_setaffinity_np

**Status:** Accepted  
**Date:** 2026-06-06

## Context

The dev Stash container is Alpine Linux (musl libc). PyTorch's manylinux wheel bundles its own `libgomp-<hash>.so.1` (OpenMP runtime) compiled against glibc. That library references `pthread_attr_setaffinity_np`, a GNU extension used to pin OpenMP worker threads to specific CPUs.

Alpine's musl libc does not implement this function. The `gcompat` package provides a glibc shim layer, but does not stub `pthread_attr_setaffinity_np`. Result: importing `torch` or `ultralytics` raises:

```
OSError: Error relocating .../torch/lib/libgomp-a34b3233.so.1:
    pthread_attr_setaffinity_np: symbol not found
```

This happens at `dlopen` time — before any Python code runs — so Python-level workarounds (env vars, `torch.set_num_threads`, etc.) cannot intercept it.

## Decision

Compile a minimal shared library containing a no-op stub:

```c
int pthread_attr_setaffinity_np(void *a, unsigned long b, void *c) { return 0; }
```

and set `ENV LD_PRELOAD=/usr/local/lib/libgomp_stub.so` in the Dockerfile so the stub is loaded into every process at startup, making the symbol available in the global symbol table before `libgomp` attempts to resolve it.

## Alternatives considered

**Replace torch's bundled libgomp with Alpine's system libgomp** (`apk add libgomp; cp /usr/lib/libgomp.so.1 <torch-lib-path>/libgomp-*.so.1`): works, but the SONAME mismatch and potential ABI differences between GCC versions make this fragile across PyTorch updates.

**patchelf to remove the symbol dependency**: requires patchelf in the image and is brittle across PyTorch wheel rebuilds that produce new libgomp file names.

**glibc-based base image** (e.g. Debian slim): would eliminate all Alpine/musl compatibility issues, but the production Stash image is Alpine-based, and we want the dev image to match production as closely as possible.

## Consequences

- The stub returns 0 (success) for all calls to `pthread_attr_setaffinity_np`. In practice this means OpenMP worker threads will not be pinned to specific CPUs. For single-image ML inference this has no meaningful performance impact.
- `LD_PRELOAD` applies to all processes in the container, including Stash itself (a Go binary). Go does not use this function, so there is no risk of behavioural change in Stash.
- If PyTorch is upgraded and the new wheel no longer bundles a glibc-linked libgomp (e.g. if a musl wheel becomes available), the stub remains harmless.
