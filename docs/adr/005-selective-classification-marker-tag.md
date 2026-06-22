# ADR-005: Selective Classification via Marker Tag

**Status:** Accepted
**Date:** 2026-06-22

## Context

The bulk classification tasks iterate the entire image library. For libraries with 10,000+ images this is prohibitively slow when the user only wants to classify a specific gallery, studio, or recently imported folder. Stash does not expose a native "tagger" UI for images equivalent to its scene/performer tagger views, so there is no built-in way to classify a subset.

## Decision

Implement a marker-tag workflow:

1. The user applies the tag `percepttag:pending` to any images they want classified — using Stash's native bulk-select UI to tag a whole gallery or studio in a few clicks.
2. A new task variant **Classify Marked Images** (`tagged_only: true`) fetches only images carrying `percepttag:pending` via Stash's `ImageFilterType` GraphQL filter.
3. After classifying each image, the plugin swaps the marker to `percepttag:done` in the same `imageUpdate` mutation that applies the classifier tags (one mutation per image).

### Design choices

**Image-level marker (not gallery/studio-level):** Applying the tag to individual images keeps the plugin's GraphQL surface minimal — a single `findImages(image_filter: { tags: ... })` query. Gallery/studio-level markers would require separate `findGalleries` / `findStudios` queries plus traversal to their child images. Since Stash's bulk-select handles "apply to all images in a gallery" natively, the image-level approach has equivalent UX at lower implementation complexity.

**Always fetch page 1:** In `tagged_only` mode the page counter is never incremented. As images are processed and `percepttag:pending` is removed, they fall out of the `ImageFilterType` filter — re-fetching page 1 naturally yields the next unprocessed batch. Incrementing pages would require coordinating the page offset with removals, which is error-prone.

**Unconditional marker swap:** The `percepttag:pending` → `percepttag:done` swap occurs for every image the task touches, including images with no resolvable file path (which are otherwise skipped). This prevents "stuck" images that would otherwise reappear in every subsequent batch.

**Tag namespace prefix (`percepttag:`):** The colon-prefixed naming makes it immediately clear in the Stash tag list that these are plugin-managed markers, reducing the risk of users accidentally conflicting with their own tags.

## Consequences

- Users with large libraries can classify any slice of images without waiting for a full library scan.
- The `percepttag:done` marker provides a lightweight audit trail of what has been selectively classified.
- Two new tag IDs (`percepttag:pending`, `percepttag:done`) are created in Stash on first use of the task. They are not cleaned up automatically — users manage them like any other tag.
- The existing bulk task variants are unchanged; this is a purely additive feature.
