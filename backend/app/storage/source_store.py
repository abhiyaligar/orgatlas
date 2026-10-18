"""Where file bodies actually live: a Supabase Storage bucket, over its S3 API.

The knowledge graph deliberately does not hold file contents. It holds the
address of the content -- ``{repository_id}::{path}``, the declaration line
ranges, and the commit sha the description was written against -- and this
module is what an address resolves through.

Why this is separate from the graph
-----------------------------------
A graph is optimised for traversal between small typed nodes. A 200KB source
file is not a node: it is a blob that is read constantly and written rarely,
and putting it in the graph means every answer that touches a file carries its
weight. Blobs are content-addressed and stored once, however many repositories,
commits or tools refer to them.

Why the S3 API rather than the Storage REST API
----------------------------------------------
Both reach the same bucket. The S3 endpoint is used because the credential pair
available here is an S3 access key, and requests to that endpoint are signed
with AWS Signature V4 -- which is what the key pair is for. The Storage REST API
would instead want a ``service_role`` key. Neither is sent anywhere but this
process.

Blobs are immutable
-------------------
The key is the SHA-256 of the content, so writing the same bytes twice costs one
object, and a pointer is never mutated in place. That is what makes the pointer
table meaningful: a pointer says "at this commit, this path held these bytes",
and a later ingest of the same content reuses the object rather than
duplicating it.

Nothing here exposes the bucket
------------------------------
Downloads happen server-side, through this module, so the bucket stays private
and no presigned URL is ever handed to a caller. The access key pair bypasses
row-level security and must never leave the process.

Failure is reported, never hidden
---------------------------------
An ingest that cannot store source still produces a complete graph; the graph
is the product, and source storage is an addition to it. So every failure here
raises with a cause a human can act on, and the caller decides whether to
degrade.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class SourceStorageError(RuntimeError):
    """Object storage could not be reached or refused the request."""


def is_configured() -> bool:
    """Whether source storage can be used at all.

    All three credentials are required: the endpoint without a key pair cannot
    sign a request, and half-configured storage is treated as absent rather than
    failing on first use.
    """
    return bool(
        settings.SUPABASE_S3_ENDPOINT
        and settings.SUPABASE_S3_ACCESS_KEY_ID
        and settings.SUPABASE_S3_SECRET_ACCESS_KEY
    )


def _client():
    """A boto3 client pointed at the S3-compatible endpoint, signed with SigV4."""
    if not is_configured():
        raise SourceStorageError(
            "Source storage is not configured. Set SUPABASE_S3_ENDPOINT, "
            "SUPABASE_S3_ACCESS_KEY_ID and SUPABASE_S3_SECRET_ACCESS_KEY to store "
            "and serve file bodies."
        )

    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.SUPABASE_S3_ENDPOINT.rstrip("/"),
        aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.SUPABASE_S3_SECRET_ACCESS_KEY,
        region_name=settings.SUPABASE_S3_REGION or "ap-south-1",
        # Signature V4 is the only thing this endpoint accepts for S3 requests.
        config=Config(signature_version="s3v4", retries={"max_attempts": 2}),
    )


def content_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_key(digest: str) -> str:
    """The storage key for a blob, sharded so a bucket has no single huge prefix."""
    return f"blobs/{digest[:2]}/{digest}"


def ensure_bucket(create: bool = True) -> bool:
    """Make sure the bucket exists.

    It is private by construction: a Supabase Storage bucket created through the
    S3 API has no public ACL, so there is nothing to grant. It is still created
    deliberately rather than assumed, because a scan that cannot store anything
    should say so before it has spent the whole clone.
    """
    client = _client()
    bucket = settings.SOURCE_BUCKET

    try:
        client.head_bucket(Bucket=bucket)
        return True
    except Exception as exc:
        if not _is_missing(exc) and _status_code(exc) != "403":
            raise SourceStorageError(
                f"Bucket {bucket!r} is not reachable: {_detail(exc)}"
            ) from exc

    if not create:
        return False

    try:
        client.create_bucket(Bucket=bucket)
        logger.info("Created source bucket %s", bucket)
        return True
    except Exception as exc:
        # Another ingest may have created it a moment ago, which is success.
        if _is_missing(exc) or "BucketAlreadyOwnedByYou" in _detail(exc):
            return True
        raise SourceStorageError(
            f"Could not create bucket {bucket!r}: {_detail(exc)}"
        ) from exc


def store_blob(digest: str, data: bytes, content_type: str = "text/plain; charset=utf-8") -> str:
    """Upload bytes under their own digest. Returns the storage key.

    Re-uploading identical content is a no-op at the object level because the
    key is the digest, so a second ingest of an unchanged repository does not
    duplicate a single byte.
    """
    client = _client()
    key = blob_key(digest)

    try:
        client.put_object(
            Bucket=settings.SOURCE_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except Exception as exc:
        raise SourceStorageError(
            f"Upload failed for {key[:24]}...: {_status_code(exc)} {exc}"
        ) from exc

    return key


def fetch_blob(key: str, offset: int = 0, length: Optional[int] = None) -> bytes:
    """Read bytes from a blob, optionally a single range.

    A range request is what keeps a retrieval call bounded: an agent asking for
    one function reads those lines and never downloads the rest of the file.
    """
    client = _client()

    request: Dict[str, Any] = {"Bucket": settings.SOURCE_BUCKET, "Key": key}
    if offset or length is not None:
        end = "" if length is None else str(offset + max(length, 0) - 1)
        request["Range"] = f"bytes={offset}-{end}"

    try:
        response = client.get_object(**request)
        return response["Body"].read()
    except Exception as exc:
        if _is_missing(exc):
            raise SourceStorageError(
                "That file body is not in storage. It may predate source storage, "
                "or its ingest may have been interrupted."
            ) from exc
        raise SourceStorageError(
            f"Read failed for {key[:24]}...: {_detail(exc)}"
        ) from exc


def read_text(key: str, offset: int = 0, length: Optional[int] = None) -> str:
    """Decode a blob as UTF-8, replacing what is not decodable rather than failing."""
    return fetch_blob(key, offset=offset, length=length).decode("utf-8", errors="replace")


def eligible_files(
    candidates: Iterable[Dict[str, Any]],
    max_file_bytes: Optional[int] = None,
    max_total_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Split candidate files into those worth storing and those that are not.

    Bounds are applied in path order so the result is reproducible rather than
    dependent on filesystem ordering, and everything dropped is reported: a file
    that was not stored must be distinguishable from one that was.
    """
    per_file = max_file_bytes or settings.SOURCE_MAX_FILE_BYTES
    total_cap = max_total_bytes or settings.SOURCE_MAX_INGEST_BYTES

    keep: List[Dict[str, Any]] = []
    reasons: Dict[str, int] = {}
    used = 0

    for item in sorted(candidates, key=lambda entry: entry["path"]):
        text = item.get("text")
        path = item["path"]
        if not text:
            reasons["empty"] = reasons.get("empty", 0) + 1
            continue
        size = len(text.encode("utf-8"))
        if size > per_file:
            reasons["too_large"] = reasons.get("too_large", 0) + 1
            continue
        if used + size > total_cap:
            reasons["over_ingest_budget"] = reasons.get("over_ingest_budget", 0) + 1
            continue
        used += size
        keep.append({"path": path, "text": text, "bytes": size})

    return {
        "files": keep,
        "stored": len(keep),
        "bytes": used,
        "skipped": reasons,
    }


def _status_code(exc: Exception) -> int:
    """The S3 error code, as text. Names matter more than numbers here."""
    from botocore.exceptions import ClientError

    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", "")
    return type(exc).__name__


def _detail(exc: Exception) -> str:
    """A message a human can act on.

    botocore's default rendering for this endpoint was "An error occurred ()"
    with the useful part omitted, which is why the error is rebuilt here rather
    than formatted from the exception alone.
    """
    from botocore.exceptions import ClientError

    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        parts = [str(error.get("Code") or ""), str(error.get("Message") or "")]
        parts = [part for part in parts if part]
        if parts:
            return ": ".join(parts)
    return str(exc)[:200]


def _is_missing(exc: Exception) -> bool:
    code = _status_code(exc).lower()
    return code in ("404", "nosuchbucket", "nosuchkey", "notfound")