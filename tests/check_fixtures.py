"""Quick accuracy check against fixture images.

Run with:
    uv run python -m tests.check_fixtures                    # all modules
    uv run python -m tests.check_fixtures person nsfw        # selected modules
    uv run python -m tests.check_fixtures clothing           # clothing only

Files prefixed with xfail_ are known model limitations: shown as [KNOWN]
when wrong (expected), or [XPASS] when unexpectedly right. xfail_ files are
excluded from the pass/fail score.
"""
import argparse
from pathlib import Path

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_XFAIL_PREFIX = "xfail_"
_ALL_MODULES = ("person", "nsfw", "clothing")


def _images(directory: Path):
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)


def _parse_args() -> list[str]:
    parser = argparse.ArgumentParser(description="Fixture accuracy check")
    parser.add_argument(
        "modules",
        nargs="*",
        choices=list(_ALL_MODULES),
        default=list(_ALL_MODULES),
        metavar="MODULE",
        help=f"Modules to run: {', '.join(_ALL_MODULES)} (default: all)",
    )
    return parser.parse_args().modules


# ── Person detection ──────────────────────────────────────────────────────────

def run_person():
    from src.classifier import ImageClassifier

    clf = ImageClassifier()
    base = Path("tests/fixtures/person_detection")

    total = correct = 0

    for label in ("include", "exclude"):
        expect_person = label == "include"
        print(f"\n--- {label.upper()} (expect has_person={expect_person}) ---")
        for img in _images(base / label):
            is_xfail = img.name.startswith(_XFAIL_PREFIX)
            result = clf.has_person(str(img))
            ok = result == expect_person
            if is_xfail:
                status = "XPASS" if ok else "KNOWN"
            else:
                status = "OK   " if ok else "WRONG"
                total += 1
                correct += ok
            print(f"  [{status}] has_person={result}  {img.name[:70]}")

    print(f"\nPerson result: {correct}/{total} correct ({100*correct//total}%)")


# ── NSFW detection ────────────────────────────────────────────────────────────

def run_nsfw():
    from src.nsfw_classifier import NsfwClassifier

    nsfw_clf = NsfwClassifier()
    nsfw_base = Path("tests/fixtures/nsfw")

    total = correct = 0

    for label in ("explicit", "revealing", "suggestive", "clean"):
        fixture_dir = nsfw_base / label
        if not fixture_dir.exists():
            continue
        expect_tag = label if label != "clean" else None
        print(f"\n--- NSFW {label.upper()} (expect tag={expect_tag!r}) ---")
        for img in _images(fixture_dir):
            is_xfail = img.name.startswith(_XFAIL_PREFIX)
            tags = nsfw_clf.classify(str(img))
            ok = (expect_tag in tags) if expect_tag else (tags == [])
            if is_xfail:
                status = "XPASS" if ok else "KNOWN"
            else:
                status = "OK   " if ok else "WRONG"
                total += 1
                correct += ok
            print(f"  [{status}] tags={tags or '(none)'}  {img.name[:60]}")

    if total:
        print(f"\nNSFW result: {correct}/{total} correct ({100*correct//total}%)")
    else:
        print("\nNSFW result: no fixtures found — add images to tests/fixtures/nsfw/{explicit,revealing,suggestive,clean}/")


# ── Clothing detection ────────────────────────────────────────────────────────

def run_clothing():
    from src.clothing_classifier import ClothingClassifier

    clothing_clf = ClothingClassifier()
    clothing_base = Path("tests/fixtures/clothing")

    total = correct = 0

    for label in ("bikini", "swimwear", "lingerie", "sportswear", "dress", "clean"):
        fixture_dir = clothing_base / label
        if not fixture_dir.exists():
            continue
        expect_tag = label if label != "clean" else None
        print(f"\n--- CLOTHING {label.upper()} (expect tag={expect_tag!r}) ---")
        for img in _images(fixture_dir):
            is_xfail = img.name.startswith(_XFAIL_PREFIX)
            tags = clothing_clf.classify(str(img))
            ok = (expect_tag in tags) if expect_tag else (tags == [])
            if is_xfail:
                status = "XPASS" if ok else "KNOWN"
            else:
                status = "OK   " if ok else "WRONG"
                total += 1
                correct += ok
            print(f"  [{status}] tags={tags or '(none)'}  {img.name[:60]}")

    if total:
        print(f"\nClothing result: {correct}/{total} correct ({100*correct//total}%)")
    else:
        print("\nClothing result: no fixtures found — add images to tests/fixtures/clothing/{bikini,swimwear,lingerie,sportswear,dress}/")


if __name__ == "__main__":
    modules = _parse_args()
    runners = {"person": run_person, "nsfw": run_nsfw, "clothing": run_clothing}
    for module in modules:
        runners[module]()
