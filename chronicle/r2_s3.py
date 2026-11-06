"""Upload large R2 objects through R2's S3-compatible API (chronicle#409).

``wrangler r2 object put`` refuses objects above 300 MiB, so Chronicle sends
larger files here. R2 accepts requests signed with AWS Signature Version 4 in
region ``auto``. A file goes up as a multipart upload in fixed-size parts: each
part is retried on its own, and the upload is aborted if a part still fails, so
no partial object is left under the key.

Credentials come from ``R2_ACCESS_KEY_ID`` and ``R2_SECRET_ACCESS_KEY`` when
both are set, and otherwise from the ``CLOUDFLARE_API_TOKEN`` that Wrangler
already uses: Cloudflare's R2 token documentation gives that token's S3 key ID
as the token's ID and its secret as the SHA-256 of the token's value. The
account is ``CLOUDFLARE_ACCOUNT_ID``, or else the ``account_id`` that
``wrangler.toml`` pins.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
import gc
import hashlib
import hmac
import os
from pathlib import Path
import time
import tomllib
from types import TracebackType
from urllib.parse import quote
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import httpx


#: R2 takes up to 10,000 parts per upload, so 100 MiB parts reach 976 GiB.
DEFAULT_PART_SIZE_BYTES = 100 * 1024 * 1024
CLOUDFLARE_API_URL = "https://api.cloudflare.com/client/v4"
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class R2S3Error(RuntimeError):
    """An R2 S3 API request or credential lookup failed."""


@dataclass(frozen=True)
class R2Credentials:
    """An S3 API key pair for one Cloudflare account's R2 buckets."""

    account_id: str
    access_key_id: str
    secret_access_key: str = field(repr=False)

    @property
    def host(self) -> str:
        """Return the account's S3 API host."""
        return f"{self.account_id}.r2.cloudflarestorage.com"


def credentials_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    wrangler_toml: str | Path = "wrangler.toml",
    transport: httpx.BaseTransport | None = None,
) -> R2Credentials:
    """Return R2 S3 credentials from the environment (see the module docstring)."""
    environ = os.environ if environ is None else environ
    account_id = environ.get("CLOUDFLARE_ACCOUNT_ID") or _wrangler_account_id(
        Path(wrangler_toml)
    )
    if not account_id:
        raise R2S3Error(
            "No Cloudflare account: set CLOUDFLARE_ACCOUNT_ID, or run from the "
            "directory whose wrangler.toml pins account_id."
        )
    access_key_id = environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = environ.get("R2_SECRET_ACCESS_KEY")
    if access_key_id and secret_access_key:
        return R2Credentials(account_id, access_key_id, secret_access_key)
    token = environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        raise R2S3Error(
            "No R2 credentials: set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY, "
            "or CLOUDFLARE_API_TOKEN."
        )
    return R2Credentials(
        account_id,
        _api_token_id(token, account_id, transport=transport),
        hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )


def sign_v4(
    method: str,
    *,
    host: str,
    path: str,
    query: Mapping[str, str],
    headers: Mapping[str, str],
    payload_sha256: str,
    access_key_id: str,
    secret_access_key: str,
    now: datetime,
    region: str = "auto",
) -> dict[str, str]:
    """Return a request's headers with its AWS Signature Version 4.

    ``path`` is the request path already URI-encoded, as it is sent. Every
    header returned is signed: ``host``, ``x-amz-content-sha256``,
    ``x-amz-date`` and the ``headers`` given.
    """
    amz_date = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    signed = {
        **{name.lower(): " ".join(value.split()) for name, value in headers.items()},
        "host": host,
        "x-amz-content-sha256": payload_sha256,
        "x-amz-date": amz_date,
    }
    names = sorted(signed)
    signed_names = ";".join(names)
    canonical_request = "\n".join(
        [
            method,
            path,
            canonical_query(query),
            "".join(f"{name}:{signed[name]}\n" for name in names),
            signed_names,
            payload_sha256,
        ]
    )
    scope = f"{amz_date[:8]}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    key = f"AWS4{secret_access_key}".encode("utf-8")
    for part in (amz_date[:8], region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    signature = hmac.new(
        key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {
        **signed,
        "authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key_id}/{scope}, "
            f"SignedHeaders={signed_names}, Signature={signature}"
        ),
    }


def canonical_query(query: Mapping[str, str]) -> str:
    """Return a query string in Signature Version 4's canonical form."""
    return "&".join(
        f"{_uri_encode(name)}={_uri_encode(value)}"
        for name, value in sorted(query.items())
    )


class R2Client:
    """Signed S3 API requests to one Cloudflare account's R2 buckets."""

    def __init__(
        self,
        credentials: R2Credentials,
        *,
        transport: httpx.BaseTransport | None = None,
        part_size: int = DEFAULT_PART_SIZE_BYTES,
        attempts: int = 4,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if part_size <= 0 or attempts <= 0:
            raise ValueError("part_size and attempts must be positive")
        self.credentials = credentials
        self.part_size = part_size
        self.attempts = attempts
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._http = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(60.0, read=600.0, write=600.0),
        )

    def __enter__(self) -> R2Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP connection pool."""
        self._http.close()

    def put_file(
        self,
        bucket: str,
        key: str,
        path: str | Path,
        *,
        content_type: str | None = None,
    ) -> int:
        """Upload a file as a multipart upload and return its part count.

        Parts are read one at a time, so memory holds one part, not the file.
        """
        path = Path(path)
        if path.stat().st_size == 0:
            raise R2S3Error(f"A multipart upload needs a non-empty file: {path}")
        upload_id = self._create_upload(bucket, key, content_type)
        parts: list[tuple[int, str]] = []
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(self.part_size):
                    number = len(parts) + 1
                    parts.append(
                        (
                            number,
                            self._upload_part(bucket, key, upload_id, number, chunk),
                        )
                    )
                    # httpx keeps each response in a reference cycle with its
                    # request, which holds the part it sent. The cycle
                    # collector can leave those for many parts, and so most of
                    # a file in memory, so free the part before the next read.
                    del chunk
                    gc.collect()
            self._complete_upload(bucket, key, upload_id, parts)
        except BaseException:
            self._abort_upload(bucket, key, upload_id)
            raise
        return len(parts)

    def _create_upload(self, bucket: str, key: str, content_type: str | None) -> str:
        response = self._request(
            "POST",
            bucket,
            key,
            {"uploads": ""},
            headers={"content-type": content_type} if content_type else {},
        )
        upload_id = _xml_text(response, "UploadId")
        if not upload_id:
            raise R2S3Error(f"CreateMultipartUpload for {key} returned no UploadId")
        return upload_id

    def _upload_part(
        self, bucket: str, key: str, upload_id: str, number: int, chunk: bytes
    ) -> str:
        response = self._request(
            "PUT",
            bucket,
            key,
            {"partNumber": str(number), "uploadId": upload_id},
            body=chunk,
        )
        etag = response.headers.get("etag")
        if not etag:
            raise R2S3Error(f"UploadPart {number} of {key} returned no ETag")
        return etag

    def _complete_upload(
        self, bucket: str, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None:
        body = "".join(
            f"<Part><PartNumber>{number}</PartNumber><ETag>{escape(etag)}</ETag></Part>"
            for number, etag in parts
        )
        response = self._request(
            "POST",
            bucket,
            key,
            {"uploadId": upload_id},
            body=f"<CompleteMultipartUpload>{body}</CompleteMultipartUpload>".encode(
                "utf-8"
            ),
            headers={"content-type": "application/xml"},
        )
        # S3 can report a failed completion inside a 200 response.
        if _xml_root_tag(response) == "Error":
            raise R2S3Error(
                f"CompleteMultipartUpload for {key} failed: {response.text[:300]}"
            )

    def _abort_upload(self, bucket: str, key: str, upload_id: str) -> None:
        try:
            self._request("DELETE", bucket, key, {"uploadId": upload_id})
        except R2S3Error:
            # The caller's error matters more; R2 expires abandoned uploads.
            pass

    def _request(
        self,
        method: str,
        bucket: str,
        key: str,
        query: Mapping[str, str],
        *,
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        path = f"/{_uri_encode(bucket)}/{_uri_encode(key, keep_slash=True)}"
        url = f"https://{self.credentials.host}{path}"
        if query:
            url = f"{url}?{canonical_query(query)}"
        payload_sha256 = hashlib.sha256(body).hexdigest()
        for attempt in range(1, self.attempts + 1):
            signed = sign_v4(
                method,
                host=self.credentials.host,
                path=path,
                query=query,
                headers=headers or {},
                payload_sha256=payload_sha256,
                access_key_id=self.credentials.access_key_id,
                secret_access_key=self.credentials.secret_access_key,
                now=self._clock(),
            )
            try:
                response = self._http.request(method, url, content=body, headers=signed)
            except httpx.TransportError as exc:
                if attempt == self.attempts:
                    raise R2S3Error(f"{method} {key} failed: {exc}") from exc
            else:
                if response.is_success:
                    return response
                if (
                    response.status_code not in _RETRY_STATUSES
                    or attempt == self.attempts
                ):
                    raise R2S3Error(
                        f"{method} {key} returned HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )
            self._sleep(2.0**attempt)
        raise AssertionError("unreachable")


def _api_token_id(
    token: str, account_id: str, *, transport: httpx.BaseTransport | None
) -> str:
    """Return an API token's ID: user tokens and account tokens verify apart."""
    try:
        with httpx.Client(transport=transport, timeout=30.0) as client:
            for url in (
                f"{CLOUDFLARE_API_URL}/user/tokens/verify",
                f"{CLOUDFLARE_API_URL}/accounts/{account_id}/tokens/verify",
            ):
                response = client.get(url, headers={"Authorization": f"Bearer {token}"})
                if response.status_code == 200:
                    token_id = (response.json().get("result") or {}).get("id")
                    if token_id:
                        return str(token_id)
    except (httpx.HTTPError, ValueError) as exc:
        raise R2S3Error(f"Could not verify CLOUDFLARE_API_TOKEN: {exc}") from exc
    raise R2S3Error("CLOUDFLARE_API_TOKEN did not verify, so its R2 key ID is unknown.")


def _wrangler_account_id(path: Path) -> str | None:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    account_id = payload.get("account_id")
    return account_id if isinstance(account_id, str) and account_id else None


def _uri_encode(value: str, *, keep_slash: bool = False) -> str:
    return quote(value, safe="-_.~/" if keep_slash else "-_.~")


def _xml_text(response: httpx.Response, tag: str) -> str | None:
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return None
    # ``{*}`` matches the tag in S3's namespace or in none.
    element = root.find(f".//{{*}}{tag}")
    return element.text if element is not None else None


def _xml_root_tag(response: httpx.Response) -> str | None:
    if not response.content.strip():
        return None
    try:
        tag = ElementTree.fromstring(response.content).tag
    except ElementTree.ParseError:
        return None
    return tag.rsplit("}", 1)[-1]
