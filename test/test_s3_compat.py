# Copyright (c) 2026 Aiven, Helsinki, Finland. https://aiven.io/
from botocore.config import Config
from myhoard.s3_compat import register_s3_compatibility_handlers
from rohmu.object_storage.s3 import S3Transfer

import pytest

pytestmark = [pytest.mark.unittest, pytest.mark.all]


class _RequestCaptured(Exception):
    pass


def _delete_objects_headers(request_checksum_calculation: str) -> dict[str, str]:
    register_s3_compatibility_handlers()
    with S3Transfer._get_session() as session:  # pylint: disable=protected-access
        client = session.create_client(
            "s3",
            region_name="eu-west-2",
            endpoint_url="https://s3.example.invalid",
            aws_access_key_id="access",
            aws_secret_access_key="secret",
            config=Config(request_checksum_calculation=request_checksum_calculation),
        )
    captured = {}

    def capture(request, **_kwargs):
        captured.update({key.lower(): value for key, value in request.headers.items()})
        raise _RequestCaptured()

    client.meta.events.register("before-send.s3.DeleteObjects", capture)
    with pytest.raises(_RequestCaptured):
        client.delete_objects(Bucket="bucket", Delete={"Objects": [{"Key": "key"}]})
    return captured


def test_s3_compat_sends_content_md5_on_delete_objects_when_checksums_are_only_when_required() -> None:
    headers = _delete_objects_headers("when_required")

    assert "content-md5" in headers
    assert not [header for header in headers if header.startswith("x-amz-checksum-")]
    assert "x-amz-sdk-checksum-algorithm" not in headers


def test_s3_compat_keeps_flexible_checksum_on_delete_objects_by_default() -> None:
    headers = _delete_objects_headers("when_supported")

    assert "x-amz-checksum-crc32" in headers
    assert "content-md5" not in headers
