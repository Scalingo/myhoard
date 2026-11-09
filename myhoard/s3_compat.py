# Copyright (c) 2026 Aiven, Helsinki, Finland. https://aiven.io/
"""Compatibility tweaks for S3 implementations lagging behind AWS checksum changes.

Since botocore 1.36, operations flagged with ``requestChecksumRequired`` (such as ``DeleteObjects``) always get a
CRC32 flexible checksum, even when ``request_checksum_calculation`` is ``when_required``. Several S3 compatible
object storages do not support flexible checksums and still require ``Content-MD5`` on those
operations, rejecting the request with ``BadDigest``.

When the client is configured with ``request_checksum_calculation=when_required`` (``AWS_REQUEST_CHECKSUM_CALCULATION``),
the user has explicitly opted out of the new checksum defaults, so we fall back to the legacy ``Content-MD5`` header,
which AWS S3 also still accepts.
"""

from rohmu.object_storage.s3 import S3Transfer
from typing import Any

import base64
import hashlib

HANDLER_UNIQUE_ID = "myhoard-s3-legacy-content-md5"
_SDK_CHECKSUM_ALGORITHM_HEADER = "x-amz-sdk-checksum-algorithm"


def use_content_md5_for_required_checksums(params: dict[str, Any], **_kwargs: Any) -> None:
    context = params.get("context", {})
    client_config = context.get("client_config")
    if getattr(client_config, "request_checksum_calculation", None) != "when_required":
        return
    checksum_context = context.get("checksum")
    if not checksum_context or not isinstance(checksum_context.get("request_algorithm"), dict):
        return
    if _SDK_CHECKSUM_ALGORITHM_HEADER in params.get("headers", {}):
        # The caller explicitly asked for a checksum algorithm, keep it
        return
    body = params.get("body")
    if not isinstance(body, (bytes, bytearray)):
        # Streaming bodies are never subject to a required checksum with "when_required", keep botocore behavior
        return
    # Drop the flexible checksum so that botocore does not add any x-amz-checksum-* header, and send the legacy one
    del checksum_context["request_algorithm"]
    checksum_context.pop("request_algorithm_header", None)
    params["headers"]["Content-MD5"] = base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode("ascii")


def register_s3_compatibility_handlers() -> None:
    """Register handlers on rohmu's shared botocore session.

    Clients copy the session handlers when created, so this must run before any S3 client is created.
    """
    with S3Transfer._get_session() as session:  # pylint: disable=protected-access
        session.register("before-call.s3", use_content_md5_for_required_checksums, unique_id=HANDLER_UNIQUE_ID)
