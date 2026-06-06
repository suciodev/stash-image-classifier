#!/usr/bin/env python3
"""
Per-image scraper entry point for Stash.

Stash invokes this as an imageByFragment scraper: it sends the current image
data as JSON on stdin, and expects a JSON object with updated fields on stdout.
We run the person-detection classifier and return {"tags": [{"name": "exclude"}]}
if no person is found, or {} if a person is present.
"""
import json
import os
import sys

import requests

# Import the classifier from the sibling plugin directory.
# This works because both plugin and scraper are deployed under /root/.stash/:
#   scrapers/stash-image-classifier/classify.py  (this file)
#   plugins/stash-image-classifier/src/classifier.py
_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "plugins", "stash-image-classifier",
)
sys.path.insert(0, _PLUGIN_DIR)

# Redirect stdout → stderr during import so ultralytics startup messages don't
# corrupt the JSON that Stash reads from stdout.
sys.stdout = sys.stderr
from src.classifier import ImageClassifier  # noqa: E402
sys.stdout = sys.__stdout__

_TAG_NAME = "exclude"
_STASH_PORT = os.environ.get("STASH_PORT", "9999")
_STASH_URL = f"http://localhost:{_STASH_PORT}/graphql"


def _get_path_from_fragment(data: dict) -> str | None:
    """Extract the image file path from the Stash fragment payload (if present)."""
    for f in data.get("files", []):
        if p := f.get("path"):
            return p
    for f in data.get("visual_files", []):
        if p := f.get("path"):
            return p
    return data.get("url") or None


def _lookup_path_by_id(image_id: str) -> str | None:
    """Call the local Stash API to get the file path for an image ID."""
    query = """
        query FindImage($id: ID!) {
            findImage(id: $id) {
                visual_files { ... on ImageFile { path } }
            }
        }
    """
    try:
        resp = requests.post(_STASH_URL, json={"query": query, "variables": {"id": image_id}}, timeout=10)
        img = resp.json().get("data", {}).get("findImage") or {}
        for f in img.get("visual_files", []):
            if p := f.get("path"):
                return p
    except Exception:
        pass
    return None


def main():
    data = json.loads(sys.stdin.read())

    path = _get_path_from_fragment(data)
    if not path and data.get("id"):
        path = _lookup_path_by_id(data["id"])

    # Stash may store paths without a leading slash; normalise to absolute.
    if path and not os.path.isabs(path):
        path = "/" + path
    if not path or not os.path.isfile(path):
        print(json.dumps({}))
        return

    classifier = ImageClassifier()
    if classifier.has_person(path):
        print(json.dumps({}))
    else:
        print(json.dumps({"tags": [{"name": _TAG_NAME}]}))


if __name__ == "__main__":
    main()
