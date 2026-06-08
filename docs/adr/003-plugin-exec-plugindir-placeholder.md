# ADR-003: Use `{pluginDir}` placeholder in plugin exec path

**Status:** Accepted  
**Date:** 2026-06-06

## Context

When running the "Classify Images" bulk task from the Stash Tasks panel, Stash logged:

```
[Plugin / Image Classifier] /usr/local/bin/python3: can't open file '//main.py': [Errno 2] No such file or directory
Plugin returned error: exit status 2
```

The plugin manifest had:

```yaml
exec:
  - python
  - main.py
```

The plugin worked correctly when invoked manually (`cd` into the plugin directory and run `python main.py`), confirming the issue was in how Stash constructed the subprocess command.

## Root cause

Stash's plugin runner (v0.27+) does **not** automatically prepend the plugin directory to Python script arguments. It only substitutes the literal string `{pluginDir}` in exec arguments with the plugin's directory path at runtime. Without this placeholder, `main.py` is passed as-is and the fallback path construction produces `//main.py` — a path that does not exist.

Specifically, `pkg/plugin/config.go` (`getExecCommand`) iterates over exec arguments (skipping exec[0]) and calls `strings.ReplaceAll(arg, "{pluginDir}", dir)` where `dir = filepath.Dir(c.path)`. No other path injection happens for Python plugins.

This is the convention throughout CommunityScripts (e.g. `"{pluginDir}/phashDuplicateTagger.py"`).

## Decision

Use `{pluginDir}` in exec[1] so Stash resolves the absolute path at runtime:

```yaml
exec:
  - python
  - "{pluginDir}/main.py"
```

## Alternatives considered

**Set CWD and use a relative path**: Stash does not guarantee the working directory is the plugin folder for all invocation paths (task vs hook vs reload). Relying on CWD is fragile.

**Absolute path in YAML**: Hardcoding `/root/.stash/plugins/stash-image-classifier/main.py` breaks on every deployment where the plugins path differs.

## Consequences

- Any future Python scripts added to the plugin manifest must also use `"{pluginDir}/script.py"` — bare filenames will fail at runtime with the same `//script.py` error.
- Scraper exec (`script:` field in scraper YAML) is handled by a different code path and does not require this placeholder — the scraper runner sets CWD to the scraper directory.
