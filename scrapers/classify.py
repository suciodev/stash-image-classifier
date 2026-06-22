#!/usr/bin/env python3
"""
Per-image scraper entry point for Stash.

Stash invokes this as an imageByFragment scraper: it sends the current image
data as JSON on stdin, and expects a JSON object with updated fields on stdout.

Pipeline (priority order):
1. NSFW detection — if any NSFW labels fire, return those tags.
   Runs on all images, including those where person detection would miss
   the subject (e.g. partial bodies, swimmers).
2. Person detection — if no person found, return "exclude".
3. Default — person present and not NSFW; return no tags.

NSFW and exclude are mutually exclusive: an NSFW image never also receives
the exclude tag, even if no person is detected by the person classifier.
"""
import contextlib
import json
import os
import sys

import requests

# Insert the sibling plugin directory so src.* imports resolve.
# Container layout:
#   scrapers/stash-image-classifier/classify.py  (this file)
#   plugins/stash-image-classifier/src/
_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "plugins", "stash-image-classifier",
)
sys.path.insert(0, _PLUGIN_DIR)


@contextlib.contextmanager
def _suppress_stdout():
    """Redirect stdout → stderr for the duration of the block.

    onnxruntime (NudeNet) and ultralytics both print startup noise at import
    and at construction time.  Any stray byte on stdout corrupts the JSON
    that Stash reads from the scraper process.
    """
    old = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old


with _suppress_stdout():
    from src.classifier import ImageClassifier      # noqa: E402
    from src.nsfw_classifier import NsfwClassifier  # noqa: E402
    _person_clf = ImageClassifier()
    _nsfw_clf = NsfwClassifier()


_STASH_PORT = os.environ.get("STASH_PORT", "9999")
_STASH_URL = f"http://localhost:{_STASH_PORT}/graphql"


def _get_path_from_fragment(data: dict) -> str | None:
    """Extract the image file path from the Stash fragment payload (if present).

    In practice the imageByFragment fragment never includes file paths, so this
    almost always returns None and the caller falls through to _lookup_path_by_id.
    Kept as a fast-path guard for forward compatibility.
    """
    for f in data.get("files", []):
        if p := f.get("path"):
            return p
    for f in data.get("visual_files", []):
        if p := f.get("path"):
            return p
    return None


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


def _classify_image(path: str) -> dict:
    """
    Run classifiers in priority order and return the Stash scraper response dict.

    To add a future classifier (e.g. clothing style):
      - Add a call here, gated on whatever conditions apply.
      - Keep the control flow explicit rather than adding to a list.
    """
    nsfw_tags = _nsfw_clf.classify(path)
    if nsfw_tags:
        return {"tags": [{"name": t} for t in nsfw_tags]}

    if not _person_clf.has_person(path):
        return {"tags": [{"name": "exclude"}]}

    return {}


def main():
    data = json.loads(sys.stdin.read())

    path = _get_path_from_fragment(data)
    if not path and data.get("id"):
        path = _lookup_path_by_id(data["id"])

    if path and not os.path.isabs(path):
        path = "/" + path
    if not path or not os.path.isfile(path):
        print(json.dumps({}))
        return

    print(json.dumps(_classify_image(path)))


if __name__ == "__main__":
    main()
