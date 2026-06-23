import sys
import json
from pathlib import Path

from src.classifier import ImageClassifier
from src.nsfw_classifier import NsfwClassifier
from src.stash_client import StashClient
from src import log, progress

# Tags managed by this classifier. Used to detect already-classified images.
_CLASSIFIER_TAGS = ("exclude", "explicit", "revealing", "suggestive")


def main():
    raw = sys.stdin.read()
    try:
        input_data = json.loads(raw)
    except json.JSONDecodeError as e:
        log("error", f"Failed to parse input JSON: {e}")
        sys.exit(1)

    server = input_data["server_connection"]
    args = input_data.get("args", {})
    mode = args.get("mode", "classify")

    client = StashClient(server)
    classifier = ImageClassifier()
    nsfw_classifier = NsfwClassifier()

    if mode == "classify":
        run_classify(client, classifier, nsfw_classifier, args)
    elif mode == "Image.Create.Post":
        run_hook(client, classifier, nsfw_classifier, args)
    else:
        log("error", f"Unknown mode: {mode}")
        sys.exit(1)


def _classify_image(path: str, classifier: ImageClassifier, nsfw_classifier: NsfwClassifier, exclude_tag: str) -> list[str]:
    """
    Returns the list of tag names to apply to an image.

    NSFW classification runs unconditionally — needed to catch explicit images
    that YOLO misses (unusual poses not in COCO training data).
    """
    has_person = classifier.has_person(path)
    nsfw_tags = nsfw_classifier.classify(path)
    if nsfw_tags:
        return nsfw_tags
    if not has_person:
        return [exclude_tag]
    return []


def run_classify(client: "StashClient", classifier: "ImageClassifier", nsfw_classifier: "NsfwClassifier", args: dict):
    exclude_tag_name = args.get("tag_name", "exclude")
    batch_size = int(args.get("batch_size", 50))
    skip_tagged = str(args.get("skip_tagged", "false")).lower() == "true"
    recheck_exclude = str(args.get("recheck_exclude", "false")).lower() == "true"
    tagged_only = str(args.get("tagged_only", "false")).lower() == "true"

    tag_ids: dict[str, str] = {name: client.find_or_create_tag(name) for name in _CLASSIFIER_TAGS}
    if exclude_tag_name not in tag_ids:
        tag_ids[exclude_tag_name] = client.find_or_create_tag(exclude_tag_name)
    classifier_tag_id_set = set(tag_ids.values())
    nsfw_severity_tag_id_set = {tag_ids[n] for n in ("explicit", "revealing", "suggestive") if n in tag_ids}

    pending_tag_id = done_tag_id = None
    if tagged_only:
        pending_tag_id = client.find_or_create_tag("percepttag:pending")
        done_tag_id = client.find_or_create_tag("percepttag:done")
        total = client.count_images_by_tag(pending_tag_id)
        mode_label = "percepttag:pending images"
    elif skip_tagged:
        total = client.count_images()
        mode_label = "untagged images"
    elif recheck_exclude:
        total = client.count_images()
        mode_label = "exclude-tagged and untagged images"
    else:
        total = client.count_images()
        mode_label = "all images"

    log("info", f"Starting classification of {mode_label} — {total} images to process")
    progress(0.0)

    processed = 0
    tagged = 0
    cleaned = 0
    skipped = 0
    page = 1

    while processed < total:
        if tagged_only:
            # Always fetch page 1: images fall out of the filter as percepttag:pending is removed
            images = client.find_images_by_tag(pending_tag_id, page=1, per_page=batch_size)
        else:
            images = client.find_images(page=page, per_page=batch_size)

        if not images:
            break

        for image in images:
            image_path = image.get("path")
            existing_tag_ids: list[str] = image.get("tag_ids", [])
            filename = Path(image_path).name if image_path else f"id={image['id']}"

            if not tagged_only:
                if skip_tagged and classifier_tag_id_set.intersection(existing_tag_ids):
                    skipped += 1
                    processed += 1
                    progress(processed / total)
                    continue

                if recheck_exclude and nsfw_severity_tag_id_set.intersection(existing_tag_ids):
                    skipped += 1
                    processed += 1
                    progress(processed / total)
                    continue

            if not image_path:
                log("warning", f"{filename} — no path, skipping")
                if tagged_only:
                    client.update_image_tags(image["id"], [done_tag_id], [pending_tag_id], existing_tag_ids)
                processed += 1
                progress(processed / total)
                continue

            desired_tag_names = _classify_image(image_path, classifier, nsfw_classifier, exclude_tag_name)
            desired_tag_ids = [tag_ids[n] for n in desired_tag_names if n in tag_ids]

            exclude_tag_id = tag_ids[exclude_tag_name]
            stale_exclude = (
                exclude_tag_id in existing_tag_ids
                and exclude_tag_id not in desired_tag_ids
            )
            remove_ids = [exclude_tag_id] if stale_exclude else []

            if tagged_only:
                remove_ids.append(pending_tag_id)
                client.update_image_tags(
                    image["id"],
                    desired_tag_ids + [done_tag_id],
                    remove_ids,
                    existing_tag_ids,
                )
            elif desired_tag_ids or remove_ids:
                client.update_image_tags(image["id"], desired_tag_ids, remove_ids, existing_tag_ids)

            added_names = [n for n in desired_tag_names if tag_ids.get(n) not in existing_tag_ids]
            if added_names or stale_exclude:
                parts = []
                if added_names:
                    parts.append(f"added: {', '.join(added_names)}")
                if stale_exclude:
                    parts.append("removed stale: exclude")
                    cleaned += 1
                if tagged_only:
                    parts.append("marker: pending → done")
                log("info", f"{filename} — {'; '.join(parts)}")
                tagged += len(added_names)
            else:
                suffix = "; marker: pending → done" if tagged_only else ""
                log("info", f"{filename} — no change ({', '.join(desired_tag_names) or 'clean'}){suffix}")

            processed += 1
            progress(processed / total)

        if not tagged_only:
            page += 1

    summary = f"Done — {processed} processed, {tagged} tags added"
    if cleaned:
        summary += f", {cleaned} stale 'exclude' removed"
    if skipped:
        summary += f", {skipped} skipped (already tagged)"
    log("info", summary)


def run_hook(client: "StashClient", classifier: "ImageClassifier", nsfw_classifier: "NsfwClassifier", args: dict):
    hook_ctx = args.get("hookContext", {})
    image_id = str(hook_ctx.get("id") or hook_ctx.get("ID", ""))
    if not image_id:
        log("error", "Hook fired but hookContext.id is missing")
        sys.exit(1)

    image = client.find_image_by_id(image_id)
    if not image or not image.get("path"):
        log("warning", f"Image {image_id} not found or has no path — skipping")
        return

    exclude_tag_name = args.get("tag_name", "exclude")

    tag_names = _classify_image(image["path"], classifier, nsfw_classifier, exclude_tag_name)
    if tag_names:
        for tag_name in tag_names:
            tag_id = client.find_or_create_tag(tag_name)
            client.add_tag_to_image(image["id"], tag_id, existing_tag_ids=image["tag_ids"])
        log("info", f"Image {image_id} — tagged: {', '.join(tag_names)}")
    else:
        log("info", f"Image {image_id} — no tag applied (person detected, not NSFW)")


if __name__ == "__main__":
    main()
