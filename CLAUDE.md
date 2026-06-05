# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A [Stash](https://github.com/stashapp/stash) plugin that classifies images using classical ML (no neural networks) and auto-applies tags. The initial use case: tag images that contain no people with an "exclude" label, targeting Instagram media libraries.

## Development Commands

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_classifier.py::test_no_person_detected

# Lint
uv run flake8 . --max-line-length=100

# Type check
uv run mypy src/

# Add a new dependency
uv add <package>

# Run plugin manually (simulates Stash calling it)
echo '{"server_connection":{"Scheme":"http","Host":"localhost","Port":9999},"args":{"mode":"classify"}}' | uv run python main.py
```

## Stash Plugin Architecture

Stash plugins are invoked as subprocess tasks. Stash passes JSON to the plugin via **stdin** and the plugin communicates back via **stdout** using the Stash task RPC protocol. The plugin declares itself via a YAML manifest.

### Key Files

- `stash-image-classifier.yml` — Plugin manifest. Declares task modes, the exec command, and required permissions.
- `main.py` — Entry point. Reads JSON from stdin, dispatches to task handlers.
- `src/classifier.py` — Core ML classification logic (HOG + SVM or similar).
- `src/stash_client.py` — GraphQL client for querying images and applying tags via the Stash API.
- `tests/` — Unit tests for classifier and integration tests against a mock Stash API.

### Plugin Manifest Shape

```yaml
name: Image Classifier
description: Classifies images and applies tags using classical ML
url: https://github.com/...
version: 0.1.0
exec:
  - python
  - main.py
interface: raw
tasks:
  - name: Classify Images
    description: Detect persons and apply exclude tags to images without people
    defaultArgs:
      mode: classify
```

### Communication Protocol

Main receives input like:
```json
{
  "server_connection": { "Scheme": "http", "Host": "localhost", "Port": 9999, "SessionCookie": {...} },
  "args": { "mode": "classify" }
}
```

Progress and log output goes to **stderr** in the format Stash expects:
```
{"level":"info","message":"Processing image 1 of 100"}
{"progress":0.5}
```

## Classification Approach

**Constraint: fully local and offline — no AI API calls, no token costs.** Local neural network inference is fine.

Preferred stack:
- `ultralytics` (YOLOv8) — person detection; model downloads once on first run (~6MB), then cached locally
- `opencv-python` — image loading and preprocessing
- `Pillow` — fallback image handling

### Person Detection Strategy

Use YOLOv8 nano (`yolov8n.pt`) for person detection. It runs on CPU, is accurate on real-world photos, and requires no API keys:

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")  # downloads once, then cached in ~/.cache/ultralytics/
results = model(img_path, classes=[0], verbose=False)  # class 0 = person
has_person = len(results[0].boxes) > 0
```

For environments with no internet access at all, download `yolov8n.pt` once and bundle it with the plugin, then load via `YOLO("path/to/yolov8n.pt")`.

## Stash GraphQL API

The plugin interacts with Stash's local GraphQL endpoint at `http://HOST:PORT/graphql`.

Key operations:
- `findImages(filter: {...})` — paginate through the image library
- `imageUpdate(input: {...})` — apply tags to an image
- `findOrCreateTag(name: "exclude")` — get or create a tag by name

Authentication uses the `SessionCookie` from the connection JSON passed via stdin.

## Project Constraints

- **No internet access at runtime** — all models/detectors must work fully offline.
- **No AI APIs** — no calls to OpenAI, Anthropic, or any token-based service. Local model inference is fine.
- **Non-destructive** — the plugin only adds tags, never modifies or deletes image files.
- **Stash-compatible Python** — target Python 3.9+ (3.8 is EOL as of Oct 2024).
