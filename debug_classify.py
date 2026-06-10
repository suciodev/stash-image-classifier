#!/usr/bin/env python3
"""
Visualize classifier output on one image or a whole folder.

Usage:
  python debug_classify.py path/to/image.jpg --output ./debug_out/
  python debug_classify.py path/to/folder/  --output ./debug_out/

Annotations drawn:
  - YOLO: blue bounding box per person, labelled "person 0.85"
  - NudeNet: coloured bounding box per detection (red=explicit, orange=revealing,
    yellow=suggestive), labelled with the NudeNet class name and confidence
  - CLIP: text overlay with all label probabilities and the winning clothing tag
  - Bottom bar: final tags that would be applied by the plugin
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image as PILImage
import torch

sys.path.insert(0, str(Path(__file__).parent))

from src.classifier import ImageClassifier
from src.nsfw_classifier import NsfwClassifier
from src.clothing_classifier import ClothingClassifier, _LABEL_MAP, _LABELS

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FS = 0.45          # font scale
_TH = 1             # text thickness
_BW = 2             # box line thickness
_WHITE = (255, 255, 255)

# BGR colours
_COLOR = {
    "person":     (200, 80, 0),
    "explicit":   (30,  30, 220),
    "revealing":  (0,  140, 255),
    "suggestive": (0,  210, 210),
    "other":      (140, 140, 140),
}

_SEVERITY_TAG = {
    "explicit":   "explicit",
    "revealing":  "revealing",
    "suggestive": "suggestive",
}


def _box(img, x1, y1, x2, y2, color, alpha=0.55):
    """Draw a semi-transparent rectangle outline."""
    overlay = img.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, _BW)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def _label_box(img, text, x, y, color, alpha=0.55):
    """Draw text with a semi-transparent filled background rectangle."""
    (tw, th), base = cv2.getTextSize(text, _FONT, _FS, _TH)
    pt1 = (x, y - th - base - 2)
    pt2 = (x + tw + 4, y + base)
    overlay = img.copy()
    cv2.rectangle(overlay, pt1, pt2, color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    cv2.putText(img, text, (x + 2, y), _FONT, _FS, _WHITE, _TH, cv2.LINE_AA)


def _yolo_boxes(clf: ImageClassifier, path: str):
    """Return [(x1,y1,x2,y2,conf)] for person boxes passing area threshold."""
    results = clf.model(path, classes=[0], conf=clf.min_confidence, verbose=False)
    r = results[0]
    img_area = r.orig_shape[0] * r.orig_shape[1]
    boxes = []
    for box in r.boxes:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        conf = float(box.conf[0])
        if (x2 - x1) * (y2 - y1) / img_area >= clf.min_area_fraction:
            boxes.append((x1, y1, x2, y2, conf))
    return boxes


def _nudenet_detections(clf: NsfwClassifier, path: str):
    """Return [(x1,y1,x2,y2,class_label,score,severity_tag)] above threshold."""
    try:
        raw = clf.detector.detect(path)
    except Exception:
        return []
    out = []
    for det in raw:
        score = det.get("score", 0.0)
        if score < clf.min_confidence:
            continue
        label = det.get("class", "")
        severity = clf.label_map.get(label)
        box = det.get("box", [])
        if len(box) == 4:
            x, y, w, h = [int(v) for v in box]
            out.append((x, y, x + w, y + h, label, score, severity))
    return out


def _clip_probs(clf: ClothingClassifier, path: str):
    """Return [(prompt, tag_or_None, prob)] sorted by prob descending."""
    try:
        pil = PILImage.open(path).convert("RGB")
        inputs = clf._processor(text=_LABELS, images=pil, return_tensors="pt", padding=True)
        with torch.no_grad():
            logits = clf._model(**inputs).logits_per_image[0]
        probs = logits.softmax(dim=0).tolist()
        return sorted(
            [(prompt, tag, prob) for (prompt, tag), prob in zip(_LABEL_MAP, probs)],
            key=lambda x: x[2],
            reverse=True,
        )
    except Exception:
        return []


def annotate(image_path: Path, person_clf: ImageClassifier, nsfw_clf: NsfwClassifier, clothing_clf: ClothingClassifier):
    """
    Run all classifiers, draw annotations, return (bgr_array, final_tag_list).
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"cv2 could not read {image_path}")
    h, w = img.shape[:2]
    path = str(image_path)

    # ── YOLO ─────────────────────────────────────────────────────────────────
    yolo_boxes = _yolo_boxes(person_clf, path)
    has_person = bool(yolo_boxes)

    for x1, y1, x2, y2, conf in yolo_boxes:
        _box(img, x1, y1, x2, y2, _COLOR["person"])
        _label_box(img, f"person {conf:.2f}", x1, max(y1 - 3, 14), _COLOR["person"])

    # ── NudeNet ──────────────────────────────────────────────────────────────
    nude_dets = _nudenet_detections(nsfw_clf, path)
    nsfw_tags_found = sorted(
        {sev for *_, sev in nude_dets if sev},
        key=lambda t: ["explicit", "revealing", "suggestive"].index(t) if t in ["explicit", "revealing", "suggestive"] else 99,
    )

    for x1, y1, x2, y2, label, score, severity in nude_dets:
        color = _COLOR.get(severity or "other", _COLOR["other"])
        _box(img, x1, y1, x2, y2, color)
        _label_box(img, f"{label} {score:.2f}", x1, max(y1 - 3, 14), color)

    # ── CLIP ─────────────────────────────────────────────────────────────────
    clip_results = _clip_probs(clothing_clf, path) if has_person else []
    clothing_tag = None
    if clip_results:
        top_prompt, top_tag, top_prob = clip_results[0]
        if top_prob >= clothing_clf.min_confidence and top_tag:
            clothing_tag = top_tag

    # Draw CLIP probability sidebar (top 3 labels) in top-right corner
    if clip_results:
        sidebar_x = w - 240
        for i, (prompt, tag, prob) in enumerate(clip_results[:3]):
            short = tag if tag else "other"
            line = f"{short}: {prob:.2f}"
            y_pos = 16 + i * 18
            cv2.putText(img, line, (sidebar_x, y_pos), _FONT, _FS,
                        (0, 0, 0), _TH + 1, cv2.LINE_AA)
            cv2.putText(img, line, (sidebar_x, y_pos), _FONT, _FS,
                        _WHITE, _TH, cv2.LINE_AA)

    # ── Final tag decision (mirrors _classify_image) ──────────────────────────
    if not has_person and not nsfw_tags_found:
        final_tags = ["exclude"]
    else:
        clothing_tags = [clothing_tag] if clothing_tag else []
        final_tags = nsfw_tags_found + clothing_tags

    # ── Summary bar ──────────────────────────────────────────────────────────
    bar_h = 24
    overlay = img.copy()
    cv2.rectangle(overlay, (0, h - bar_h), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    summary = f"tags: {', '.join(final_tags) or '(none)'}"
    cv2.putText(img, summary, (6, h - 7), _FONT, _FS, _WHITE, _TH, cv2.LINE_AA)

    return img, final_tags


def main():
    parser = argparse.ArgumentParser(description="Visualize classifier output on images.")
    parser.add_argument("input", type=Path, help="Image file or folder")
    parser.add_argument("--output", type=Path, required=True, help="Output folder (created if missing)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} does not exist", file=sys.stderr)
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)

    print("Loading models (CLIP may download ~600 MB on first run)...")
    person_clf = ImageClassifier()
    nsfw_clf = NsfwClassifier()
    clothing_clf = ClothingClassifier()
    print("Ready.\n")

    if args.input.is_file():
        paths = [args.input]
    else:
        paths = sorted(p for p in args.input.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)

    if not paths:
        print("No images found.")
        return

    for img_path in paths:
        try:
            annotated, tags = annotate(img_path, person_clf, nsfw_clf, clothing_clf)
            out_path = args.output / img_path.name
            cv2.imwrite(str(out_path), annotated)
            tag_str = ", ".join(tags) if tags else "(none)"
            print(f"  {img_path.name:<50}  tags: {tag_str}")
        except Exception as e:
            print(f"  {img_path.name:<50}  ERROR: {e}", file=sys.stderr)

    print(f"\n{len(paths)} image(s) → {args.output}")


if __name__ == "__main__":
    main()
