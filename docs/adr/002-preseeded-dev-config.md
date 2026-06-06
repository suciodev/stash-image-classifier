# ADR-002: Pre-seeded stash-config.yml for dev container

**Status:** Accepted  
**Date:** 2026-06-06

## Context

The dev container mounts `dev-infra/stash-config/` as `/root/.stash/` so that Stash's config, plugins, and scrapers directories are visible to the host for inspection and deployment. On first start, Stash writes `/root/.stash/config.yml` owned by `root:root` with mode `0640`.

Two problems arise from letting Stash own this file:

1. **Unreadable from WSL user session**: the file is `root`-owned and readable only by root. The host user cannot read or modify it without `sudo`.

2. **`plugins_path` may be empty or wrong**: Stash infers `plugins_path` from the binary's working directory when it writes the initial config. In the container, this can resolve to an empty string or `/`. Without a valid `plugins_path`, Stash cannot discover the plugin directory at all, so no tasks or hooks will appear in the UI.

## Decision

Add a tracked file `dev-infra/stash-config.yml` (owned by the WSL user, committed to git) that contains the minimal Stash configuration with `plugins_path` and `scrapers_path` explicitly set:

```yaml
host: 0.0.0.0
port: 9995
plugins_path: /root/.stash/plugins
scrapers_path: /root/.stash/scrapers
```

Mount this file directly over the container's config path:

```yaml
volumes:
  - ./stash-config:/root/.stash          # full config dir
  - ./stash-config.yml:/root/.stash/config.yml  # override config.yml
```

Docker resolves the individual file mount after the directory mount, so `stash-config.yml` wins. When Stash reads `/root/.stash/config.yml`, it sees the correct `plugins_path`. When Stash writes updated settings through the UI, those writes go to `dev-infra/stash-config.yml` (the bind-mounted source), which is writable by the WSL user.

## Alternatives considered

**`docker exec stash-dev sh -c "echo plugins_path: ... >> /root/.stash/config.yml"`**: requires manual intervention after each container restart and does not survive `make stop-dev && make start-dev`.

**Dockerfile `CMD` wrapper that patches the config on startup**: adds complexity and runs every time, risking clobbering user changes made through the Stash UI.

**`chmod 644` on the file via a Dockerfile `RUN`**: the file doesn't exist at build time; it is created by Stash at runtime.

## Consequences

- `dev-infra/stash-config.yml` is committed to the repository and will drift from actual runtime state when users change settings through the Stash UI. This is acceptable: the file only needs to be authoritative for `plugins_path`, `scrapers_path`, `host`, and `port`. Other settings written by Stash (JWT keys, theme, etc.) persist in the file as well, but the tracked version only needs to have the correct path entries.
- `dev-infra/stash-config/` (the directory) remains gitignored, so runtime state (SQLite DB, blobs, cache) is never committed.
