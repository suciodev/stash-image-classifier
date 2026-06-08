#!/usr/bin/env python3
"""
End-to-end test for the imageByFragment scraper.

Runs outside the container, against the dev Stash instance on localhost:9995.
Calls scrapeSingleImage via the Stash GraphQL API and validates the response.

Usage:
    uv run python -m tests.test_scraper_e2e
    make test-scraper-dev
"""
import json
import subprocess
import sys

import requests

STASH_URL = "http://localhost:9995/graphql"
SCRAPER_ID = "stash-image-classifier"

# Expected outcomes: image IDs we know from fixture filenames
# 'exclude' images should get the exclude tag; 'include' images should not.
EXPECTED = {
    "exclude": True,   # fixture in exclude/ → tag should be returned
    "include": False,  # fixture in include/ → no tag
}


def gql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(STASH_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def get_sample_images() -> list[dict]:
    """Return one exclude-fixture image and one include-fixture image."""
    resp = gql("""
        query {
            findImages(filter: { per_page: 100 }) {
                images {
                    id
                    visual_files { ... on ImageFile { path } }
                }
            }
        }
    """)
    images = resp["data"]["findImages"]["images"]
    samples = {}
    for img in images:
        path = img["visual_files"][0]["path"] if img.get("visual_files") else ""
        if "exclude/" in path and "exclude" not in samples:
            samples["exclude"] = img
        # Prefer unambiguous person_ fixtures over illustration_ for reliable detection
        if "include/" in path:
            if "include" not in samples or (
                "/illustration_" in samples["include"]["visual_files"][0]["path"]
                and "/person_" in path
            ):
                samples["include"] = img
        if len(samples) == 2 and "/person_" in samples.get("include", {}).get("visual_files", [{}])[0].get("path", ""):
            break
    return samples


def scrape_image(image_id: str) -> tuple[list[str], str | None]:
    """Trigger imageByFragment scraper. Returns (tag_names, error_message)."""
    resp = gql("""
        query ScrapeSingleImage($source: ScraperSourceInput!, $input: ScrapeSingleImageInput!) {
            scrapeSingleImage(source: $source, input: $input) {
                tags { name }
            }
        }
    """, {
        "source": {"scraper_id": SCRAPER_ID},
        "input": {"image_id": image_id},
    })
    if "errors" in resp:
        return [], resp["errors"][0]["message"]
    results = resp.get("data", {}).get("scrapeSingleImage") or []
    tags = results[0].get("tags") or [] if results else []
    return [t["name"] for t in tags], None


def main():
    print(f"Connecting to Stash at {STASH_URL} ...")
    try:
        ver = gql("{ version { version } }")["data"]["version"]["version"]
        print(f"  Stash {ver} — OK")
    except Exception as e:
        print(f"  FAIL: cannot reach Stash — {e}")
        sys.exit(1)

    print(f"\nFinding sample fixture images ...")
    samples = get_sample_images()
    if not samples:
        print("  FAIL: no fixture images found — scan /data/fixtures in the Stash UI first")
        sys.exit(1)
    for label, img in samples.items():
        path = img["visual_files"][0]["path"] if img.get("visual_files") else "?"
        print(f"  [{label}] id={img['id']}  {path}")

    print(f"\nRunning scraper '{SCRAPER_ID}' ...")
    passed = 0
    failed = 0
    for label, img in samples.items():
        tags, err = scrape_image(img["id"])
        if err:
            print(f"  [FAIL] {label} image → scraper error: {err}")
            failed += 1
            continue
        has_exclude = "exclude" in tags
        want_exclude = EXPECTED[label]
        status = "PASS" if has_exclude == want_exclude else "FAIL"
        print(f"  [{status}] {label} image → tags={tags or '(none)'}"
              f"  (expected {'exclude' if want_exclude else 'no tag'})")
        if status == "PASS":
            passed += 1
        else:
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
