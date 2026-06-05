import sys
import json

from src.classifier import ImageClassifier
from src.stash_client import StashClient
from src import log, progress


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

    if mode == "classify":
        run_classify(client, classifier, args)
    else:
        log("error", f"Unknown mode: {mode}")
        sys.exit(1)


def run_classify(client: "StashClient", classifier: "ImageClassifier", args: dict):
    tag_name = args.get("tag_name", "exclude")
    batch_size = int(args.get("batch_size", 50))

    tag_id = client.find_or_create_tag(tag_name)
    log("info", f"Using tag '{tag_name}' (id={tag_id})")

    total = client.count_images()
    log("info", f"Found {total} images to process")

    processed = 0
    tagged = 0
    page = 1

    while processed < total:
        images = client.find_images(page=page, per_page=batch_size)
        if not images:
            break

        for image in images:
            image_path = image.get("path") or image.get("visual_files", [{}])[0].get("path")
            if not image_path:
                processed += 1
                continue

            has_person = classifier.has_person(image_path)
            if not has_person:
                client.add_tag_to_image(image["id"], tag_id)
                tagged += 1

            processed += 1
            progress(processed / total)

        page += 1

    log("info", f"Done. Processed {processed} images, tagged {tagged} as '{tag_name}'.")


if __name__ == "__main__":
    main()
