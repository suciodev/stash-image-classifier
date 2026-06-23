from unittest.mock import MagicMock, call
from main import run_classify, run_hook


def _make_client(images_by_call, count=1):
    client = MagicMock()
    _counter = [0]
    _tag_map = {}

    def find_or_create(name):
        if name not in _tag_map:
            _counter[0] += 1
            _tag_map[name] = f"tid-{_counter[0]}"
        return _tag_map[name]

    client.find_or_create_tag.side_effect = find_or_create
    client._tag_map = _tag_map
    client.count_images_by_tag.return_value = count
    client.find_images_by_tag.side_effect = images_by_call
    return client


def _make_classifiers(has_person=False, nsfw_tags=None):
    clf = MagicMock()
    clf.has_person.return_value = has_person
    nsfw = MagicMock()
    nsfw.classify.return_value = nsfw_tags or []
    return clf, nsfw


def _make_hook_client(image):
    client = MagicMock()
    client.find_image_by_id.return_value = image
    _tag_map = {}
    _counter = [0]

    def find_or_create(name):
        if name not in _tag_map:
            _counter[0] += 1
            _tag_map[name] = f"tid-{_counter[0]}"
        return _tag_map[name]

    client.find_or_create_tag.side_effect = find_or_create
    client._tag_map = _tag_map
    return client


def test_hook_tags_exclude_when_no_person_no_nsfw():
    image = {"id": "1", "path": "/data/landscape.jpg", "tag_ids": []}
    client = _make_hook_client(image)
    clf, nsfw = _make_classifiers(has_person=False, nsfw_tags=[])

    run_hook(client, clf, nsfw, {"hookContext": {"id": 1}})

    tag_id = client._tag_map["exclude"]
    client.add_tag_to_image.assert_called_once_with("1", tag_id, existing_tag_ids=[])


def test_hook_applies_nsfw_tag_even_when_person_present():
    """NsfwClassifier must run unconditionally — person detected does not skip NSFW check."""
    image = {"id": "2", "path": "/data/explicit.jpg", "tag_ids": []}
    client = _make_hook_client(image)
    clf, nsfw = _make_classifiers(has_person=True, nsfw_tags=["explicit"])

    run_hook(client, clf, nsfw, {"hookContext": {"id": 2}})

    nsfw.classify.assert_called_once()
    tag_id = client._tag_map["explicit"]
    client.add_tag_to_image.assert_called_once_with("2", tag_id, existing_tag_ids=[])


def test_hook_applies_nsfw_tag_when_no_person_and_nsfw():
    image = {"id": "3", "path": "/data/revealing.jpg", "tag_ids": []}
    client = _make_hook_client(image)
    clf, nsfw = _make_classifiers(has_person=False, nsfw_tags=["revealing"])

    run_hook(client, clf, nsfw, {"hookContext": {"id": 3}})

    tag_id = client._tag_map["revealing"]
    client.add_tag_to_image.assert_called_once_with("3", tag_id, existing_tag_ids=[])
    assert "exclude" not in client._tag_map


def test_hook_applies_no_tag_when_person_and_not_nsfw():
    image = {"id": "4", "path": "/data/person.jpg", "tag_ids": []}
    client = _make_hook_client(image)
    clf, nsfw = _make_classifiers(has_person=True, nsfw_tags=[])

    run_hook(client, clf, nsfw, {"hookContext": {"id": 4}})

    client.add_tag_to_image.assert_not_called()


def test_hook_skips_image_with_no_path():
    client = _make_hook_client({"id": "5", "path": None, "tag_ids": []})
    clf, nsfw = _make_classifiers()

    run_hook(client, clf, nsfw, {"hookContext": {"id": 5}})

    client.add_tag_to_image.assert_not_called()
    clf.has_person.assert_not_called()


def test_classify_marked_images_applies_classifier_tag_and_swaps_marker():
    """Image with no person gets 'exclude' added; marker swapped pending→done in one call."""
    client = _make_client(
        images_by_call=[
            [{"id": "img-1", "path": "/data/no_person.jpg", "tag_ids": []}],
            [],
        ],
        count=1,
    )
    clf, nsfw = _make_classifiers(has_person=False)

    run_classify(client, clf, nsfw, {"tagged_only": "true"})

    tag_map = client._tag_map
    client.update_image_tags.assert_called_once()
    image_id, add_ids, remove_ids, _ = client.update_image_tags.call_args[0]
    assert image_id == "img-1"
    assert tag_map["exclude"] in add_ids
    assert tag_map["percepttag:done"] in add_ids
    assert tag_map["percepttag:pending"] in remove_ids


def test_classify_marked_images_swaps_marker_when_no_classifier_tags_change():
    """Image with person detected gets no classifier tag; marker still swapped pending→done."""
    client = _make_client(
        images_by_call=[
            [{"id": "img-1", "path": "/data/person.jpg", "tag_ids": []}],
            [],
        ],
        count=1,
    )
    clf, nsfw = _make_classifiers(has_person=True)

    run_classify(client, clf, nsfw, {"tagged_only": "true"})

    tag_map = client._tag_map
    client.update_image_tags.assert_called_once()
    image_id, add_ids, remove_ids, _ = client.update_image_tags.call_args[0]
    assert image_id == "img-1"
    assert tag_map["percepttag:done"] in add_ids
    assert tag_map["percepttag:pending"] in remove_ids
    assert tag_map.get("exclude") not in add_ids
