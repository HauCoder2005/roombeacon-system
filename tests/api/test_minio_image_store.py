"""MinIO adapter: prefix listing, key validation, size/type guards, error translation."""

import io

from botocore.exceptions import ClientError
import pytest

from roombeacon_api.domain.errors import DependencyUnavailableError
from roombeacon_api.infrastructure.minio_image_store import MAX_IMAGE_BYTES, MinioImageStore


class FakeS3:
    def __init__(self, keys=(), objects=None, error=None):
        self.keys = list(keys)
        self.objects = objects or {}
        self.error = error
        self.list_calls = []

    def list_objects_v2(self, **kwargs):
        if self.error:
            raise self.error
        self.list_calls.append(kwargs)
        prefix = kwargs.get("Prefix", "")
        keys = [k for k in self.keys if k.startswith(prefix)]
        if kwargs.get("Delimiter") == "/":
            common = sorted({prefix + k[len(prefix):].split("/", 1)[0] + "/" for k in keys if "/" in k[len(prefix):]})
            return {"CommonPrefixes": [{"Prefix": p} for p in common], "IsTruncated": False}
        return {"Contents": [{"Key": k, "Size": 10} for k in keys], "IsTruncated": False}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body, content_type, length = self.objects[Key]
        return {"Body": io.BytesIO(body), "ContentType": content_type, "ContentLength": length, "ETag": '"e"'}


def store(s3, clock=lambda: 0.0):
    return MinioImageStore(bucket="roombeacon-assets", client=s3, clock=clock)


def test_lists_only_well_formed_keys_in_position_order():
    s3 = FakeS3(keys=[
        "phongtro123/pr7/img_2_bbbbbbbb.jpg",
        "phongtro123/pr7/img_1_aaaaaaaa.webp",
        "phongtro123/pr7/notes.txt",
        "phongtro123/pr7/img_3_zzzz.jpg",
        "phongtro123/pr70/img_1_cccccccc.jpg",
    ])

    refs = store(s3).list_images("phongtro123", "pr7")

    assert [(r.position, r.key) for r in refs] == [
        (1, "phongtro123/pr7/img_1_aaaaaaaa.webp"), (2, "phongtro123/pr7/img_2_bbbbbbbb.jpg"),
    ]
    assert s3.list_calls[0]["Prefix"] == "phongtro123/pr7/"


def test_unsafe_identifiers_never_reach_s3():
    s3 = FakeS3(keys=["x/y/img_1_aaaaaaaa.jpg"])

    assert store(s3).list_images("../etc", "pr7") == []
    assert store(s3).list_images("phongtro123", "a/../b") == []
    assert s3.list_calls == []


def test_listing_results_are_cached_for_a_while():
    now = [0.0]
    s3 = FakeS3(keys=["s/1/img_1_aaaaaaaa.jpg"])
    images = store(s3, clock=lambda: now[0])

    images.list_images("s", "1"); images.list_images("s", "1")
    assert len(s3.list_calls) == 1
    now[0] = 10_000.0
    images.list_images("s", "1")
    assert len(s3.list_calls) == 2


def test_get_image_guards_type_size_and_missing_keys():
    s3 = FakeS3(objects={
        "s/1/img_1_aaaaaaaa.jpg": (b"\xff\xd8", "image/jpeg", 2),
        "s/1/img_2_bbbbbbbb.jpg": (b"<html>", "text/html", 6),
        "s/1/img_3_cccccccc.jpg": (b"", "image/jpeg", MAX_IMAGE_BYTES + 1),
    })
    images = store(s3)

    ok = images.get_image("s/1/img_1_aaaaaaaa.jpg")
    assert ok.content == b"\xff\xd8" and ok.content_type == "image/jpeg"
    assert images.get_image("s/1/img_2_bbbbbbbb.jpg") is None
    assert images.get_image("s/1/img_3_cccccccc.jpg") is None
    assert images.get_image("s/1/img_9_dddddddd.jpg") is None


def test_storage_errors_become_dependency_outages():
    s3 = FakeS3(error=ClientError({"Error": {"Code": "AccessDenied", "Message": "secret=abc"}}, "ListObjectsV2"))

    with pytest.raises(DependencyUnavailableError) as raised:
        store(s3).list_images("s", "1")
    assert "secret" not in str(raised.value)


def test_index_of_listings_with_images_is_built_from_prefixes_and_cached():
    s3 = FakeS3(keys=[
        "phongtro123/pr7/img_1_aaaaaaaa.jpg",
        "phongtro123/pr8/img_1_bbbbbbbb.jpg",
        "mogi/55/img_2_cccccccc.webp",
        "../evil/img_1_dddddddd.jpg",
    ])
    images = store(s3)

    assert images.listings_with_images() == frozenset({("phongtro123", "pr7"), ("phongtro123", "pr8"), ("mogi", "55")})
    calls = len(s3.list_calls)
    images.listings_with_images()
    assert len(s3.list_calls) == calls
