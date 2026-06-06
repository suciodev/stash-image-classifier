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

# Import the classifier from the sibling plugin directory.
# This works because both plugin and scraper are deployed under /root/.stash/:
#   scrapers/stash-image-classifier/classify.py  (this file)
#   plugins/stash-image-classifier/src/classifier.py
_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "plugins", "stash-image-classifier",
)
sys.path.insert(0, _PLUGIN_DIR)

from src.classifier import ImageClassifier  # noqa: E402

_TAG_NAME = "exclude"


def _get_path(data: dict) -> str | None:
    """Extract the image file path from the Stash fragment payload."""
    # Stash sends a Files list on the scraped object
    for f in data.get("files", []):
        if p := f.get("path"):
            return p
    # Fallback: visual_files shape (GraphQL style)
    for f in data.get("visual_files", []):
        if p := f.get("path"):
            return p
    return data.get("url")


def main():
    data = json.loads(sys.stdin.read())
    path = _get_path(data)

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
