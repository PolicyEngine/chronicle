"""Tests for Chronicle's large-file path to R2 through its S3 API (chronicle#409)."""

from __future__ import annotations

from datetime import UTC, datetime
import gc
import hashlib
from pathlib import Path
import tracemalloc

import httpx
import pytest

from chronicle.r2_s3 import (
    R2Client,
    R2Credentials,
    R2S3Error,
    canonical_query,
    credentials_from_environment,
    sign_v4,
)


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
CREDENTIALS = R2Credentials("account", "key-id", "secret")


@pytest.mark.parametrize(
    ("method", "path", "query", "headers", "payload", "signature"),
    [
        # The three Signature Version 4 examples in AWS's S3 API reference
        # ("Authenticating Requests: Using the Authorization Header").
        (
            "GET",
            "/test.txt",
            {},
            {"Range": "bytes=0-9"},
            b"",
            "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41",
        ),
        (
            "GET",
            "/",
            {"max-keys": "2", "prefix": "J"},
            {},
            b"",
            "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7",
        ),
        (
            "PUT",
            "/test%24file.text",
            {},
            {
                "Date": "Fri, 24 May 2013 00:00:00 GMT",
                "x-amz-storage-class": "REDUCED_REDUNDANCY",
            },
            b"Welcome to Amazon S3.",
            "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd",
        ),
    ],
)
def test_sign_v4_reproduces_the_aws_examples(
    method, path, query, headers, payload, signature
):
    signed = sign_v4(
        method,
        host="examplebucket.s3.amazonaws.com",
        path=path,
        query=query,
        headers=headers,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        now=datetime(2013, 5, 24, tzinfo=UTC),
        region="us-east-1",
    )

    assert signed["authorization"].endswith(f"Signature={signature}")
    assert signed["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/"
        "aws4_request, SignedHeaders="
    )


def test_canonical_query_sorts_names_and_encodes_values():
    assert canonical_query({"uploadId": "a+b/c=", "partNumber": "2"}) == (
        "partNumber=2&uploadId=a%2Bb%2Fc%3D"
    )
    assert canonical_query({"uploads": ""}) == "uploads="


class FakeR2:
    """An in-memory S3 multipart endpoint that records every request."""

    def __init__(self, fail_part: dict[int, list[int]] | None = None):
        self.requests: list[httpx.Request] = []
        self.parts: dict[int, bytes] = {}
        self.fail_part = fail_part or {}
        self.complete_status = 200
        self.complete_body = b"<CompleteMultipartUploadResult/>"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        query = dict(request.url.params)
        assert (
            request.headers["x-amz-content-sha256"]
            == hashlib.sha256(request.content).hexdigest()
        )
        assert request.headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=key-id/"
        )
        if request.method == "POST" and "uploads" in query:
            return httpx.Response(
                200,
                content=(
                    b'<InitiateMultipartUploadResult xmlns="http://s3.amazonaws.com/'
                    b'doc/2006-03-01/"><UploadId>up+1/=</UploadId>'
                    b"</InitiateMultipartUploadResult>"
                ),
            )
        if request.method == "PUT":
            number = int(query["partNumber"])
            statuses = self.fail_part.get(number, [])
            if statuses:
                return httpx.Response(statuses.pop(0))
            self.parts[number] = request.content
            return httpx.Response(200, headers={"ETag": f'"etag-{number}"'})
        if request.method == "POST":
            return httpx.Response(self.complete_status, content=self.complete_body)
        if request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def client(self, **kwargs) -> R2Client:
        return R2Client(
            CREDENTIALS,
            transport=httpx.MockTransport(self.handler),
            part_size=5,
            sleep=lambda seconds: None,
            **kwargs,
        )


def _file(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "bundle.zip"
    path.write_bytes(content)
    return path


def test_put_file_uploads_fixed_size_parts_and_completes_them_in_order(tmp_path):
    fake = FakeR2()

    with fake.client() as client:
        parts = client.put_file(
            "ledger-raw",
            "raw/uk/ucl/pkg/bundle_1/digest/bundle.zip",
            _file(tmp_path, b"abcdefghijkl"),
            content_type="application/zip",
        )

    assert parts == 3
    assert fake.parts == {1: b"abcde", 2: b"fghij", 3: b"kl"}
    create, *uploads, complete = fake.requests
    assert create.url.path == "/ledger-raw/raw/uk/ucl/pkg/bundle_1/digest/bundle.zip"
    assert create.url.query == b"uploads="
    assert create.headers["content-type"] == "application/zip"
    assert [request.url.query for request in uploads] == [
        f"partNumber={number}&uploadId=up%2B1%2F%3D".encode() for number in (1, 2, 3)
    ]
    assert complete.url.query == b"uploadId=up%2B1%2F%3D"
    assert complete.content == (
        b"<CompleteMultipartUpload>"
        b'<Part><PartNumber>1</PartNumber><ETag>"etag-1"</ETag></Part>'
        b'<Part><PartNumber>2</PartNumber><ETag>"etag-2"</ETag></Part>'
        b'<Part><PartNumber>3</PartNumber><ETag>"etag-3"</ETag></Part>'
        b"</CompleteMultipartUpload>"
    )


def test_put_file_retries_a_failed_part_on_its_own(tmp_path):
    fake = FakeR2(fail_part={2: [503, 500]})

    with fake.client() as client:
        client.put_file("ledger-raw", "key", _file(tmp_path, b"abcdefghijkl"))

    part_numbers = [
        request.url.params["partNumber"]
        for request in fake.requests
        if request.method == "PUT"
    ]
    assert part_numbers == ["1", "2", "2", "2", "3"]
    assert fake.parts == {1: b"abcde", 2: b"fghij", 3: b"kl"}


@pytest.mark.parametrize("statuses", [[403], [503, 503, 503, 503]])
def test_put_file_aborts_the_upload_when_a_part_fails(tmp_path, statuses):
    fake = FakeR2(fail_part={2: statuses})

    with fake.client() as client, pytest.raises(R2S3Error, match="HTTP"):
        client.put_file("ledger-raw", "key", _file(tmp_path, b"abcdefghijkl"))

    assert [request.method for request in fake.requests][-1] == "DELETE"
    assert fake.requests[-1].url.query == b"uploadId=up%2B1%2F%3D"
    assert 3 not in fake.parts
    assert not any(
        request.method == "POST" and "uploadId" in request.url.params
        for request in fake.requests
    )


def test_put_file_fails_on_an_error_inside_a_successful_completion(tmp_path):
    fake = FakeR2()
    fake.complete_body = b"<Error><Code>InternalError</Code></Error>"

    with fake.client() as client, pytest.raises(R2S3Error, match="InternalError"):
        client.put_file("ledger-raw", "key", _file(tmp_path, b"abcdefghijkl"))

    assert fake.requests[-1].method == "DELETE"


def test_put_file_frees_each_part_before_reading_the_next(tmp_path):
    # httpx keeps each response in a reference cycle with its request, which
    # holds the part it sent. With the cycle collector off, every part would
    # stay in memory unless put_file frees it.
    part_size = 1 << 20
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            sizes.append(len(request.content))
            return httpx.Response(200, headers={"ETag": '"etag"'})
        if "uploads" in request.url.params:
            return httpx.Response(200, content=b"<R><UploadId>up</UploadId></R>")
        return httpx.Response(200, content=b"<CompleteMultipartUploadResult/>")

    path = _file(tmp_path, bytes(8 * part_size))
    client = R2Client(
        CREDENTIALS, transport=httpx.MockTransport(handler), part_size=part_size
    )
    gc.disable()
    tracemalloc.start()
    try:
        with client:
            client.put_file("ledger-raw", "key", path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        gc.enable()

    assert sizes == [part_size] * 8
    assert peak < 3 * part_size


def test_put_file_refuses_an_empty_file(tmp_path):
    fake = FakeR2()

    with fake.client() as client, pytest.raises(R2S3Error, match="non-empty"):
        client.put_file("ledger-raw", "key", _file(tmp_path, b""))

    assert fake.requests == []


def test_explicit_r2_keys_need_no_token_lookup(tmp_path):
    credentials = credentials_from_environment(
        {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "R2_ACCESS_KEY_ID": "key-id",
            "R2_SECRET_ACCESS_KEY": "secret",
            "CLOUDFLARE_API_TOKEN": "unused",
        },
        wrangler_toml=tmp_path / "absent.toml",
        transport=httpx.MockTransport(
            lambda request: pytest.fail("no Cloudflare API call expected")
        ),
    )

    assert credentials == R2Credentials("account", "key-id", "secret")
    assert credentials.host == "account.r2.cloudflarestorage.com"
    assert "secret" not in repr(credentials)


@pytest.mark.parametrize("user_status", [200, 401])
def test_api_token_gives_the_key_pair_and_wrangler_toml_the_account(
    tmp_path, user_status
):
    wrangler_toml = tmp_path / "wrangler.toml"
    wrangler_toml.write_text('name = "chronicle"\naccount_id = "acct-123"\n')
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.headers["authorization"] == "Bearer token-value"
        if request.url.path == "/client/v4/user/tokens/verify" and user_status != 200:
            return httpx.Response(user_status, json={"success": False})
        return httpx.Response(200, json={"result": {"id": "token-id"}})

    credentials = credentials_from_environment(
        {"CLOUDFLARE_API_TOKEN": "token-value"},
        wrangler_toml=wrangler_toml,
        transport=httpx.MockTransport(handler),
    )

    assert credentials == R2Credentials(
        "acct-123", "token-id", hashlib.sha256(b"token-value").hexdigest()
    )
    expected_paths = ["/client/v4/user/tokens/verify"]
    if user_status != 200:
        expected_paths.append("/client/v4/accounts/acct-123/tokens/verify")
    assert seen == expected_paths


def test_a_token_lookup_that_cannot_reach_cloudflare_is_reported(tmp_path):
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(R2S3Error, match="Could not verify"):
        credentials_from_environment(
            {"CLOUDFLARE_ACCOUNT_ID": "account", "CLOUDFLARE_API_TOKEN": "token"},
            wrangler_toml=tmp_path / "absent.toml",
            transport=httpx.MockTransport(unreachable),
        )


def test_an_unreadable_create_response_is_an_r2_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not xml")

    client = R2Client(CREDENTIALS, transport=httpx.MockTransport(handler))
    with client, pytest.raises(R2S3Error, match="no UploadId"):
        client.put_file("ledger-raw", "key", _file(tmp_path, b"abc"))


@pytest.mark.parametrize(
    ("environ", "message"),
    [
        ({"CLOUDFLARE_API_TOKEN": "token"}, "No Cloudflare account"),
        ({"CLOUDFLARE_ACCOUNT_ID": "account"}, "No R2 credentials"),
    ],
)
def test_missing_credentials_are_reported(tmp_path, environ, message):
    with pytest.raises(R2S3Error, match=message):
        credentials_from_environment(environ, wrangler_toml=tmp_path / "absent.toml")
