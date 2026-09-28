"""Production RFC 3161 responder pins, checked against a real receipt.

A TSA replaces its responder certificate about once a year, and the append
gate refuses every receipt the new responder signs until its certificate is
pinned. The receipt under tests/fixtures/production_tsa was issued by
DigiCert's 2026 responder; it verifies offline against the committed root.
"""

from __future__ import annotations

import dataclasses
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import receipt.release_chain as receipt_release_chain

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ANCHORS = ROOT / "releases" / "anchors"
PROBE = ROOT / "tests" / "fixtures" / "production_tsa" / "digicert-2026-responder-probe"

sys.path.insert(0, str(ROOT / "scripts"))

from receipt_pins import LEDGER_SPEC  # noqa: E402
from verify_release_chain import ReleaseChainError, verify_receipt  # noqa: E402

# Releases 0000 to 0020 carry this responder's receipts.
DIGICERT_JOURNAL_RESPONDER = (
    "4aa03fa22cd75c84c55c938f828e676b9caecab33fe36d269aa334f146110a33",
    "7abda95ed7301ac94bded350babc319903d0b4f16c4e7e39346dba5f9e992b72",
)
# "DigiCert SHA256 RSA4096 Timestamp Responder 2026 1".
DIGICERT_2026_RESPONDER = (
    "2da09da7f4131f9fe72db6c5e6e9c9656755af043f1ea742cc0d2120e141ebfc",
    "753596b60a629061144cbd312017bbfb77510eac20b7eadc5fafb7cabe142fd5",
)


def _probe_digest() -> str:
    return hashlib.sha256(PROBE.with_suffix(".txt").read_bytes()).hexdigest()


def test_digicert_keeps_the_responder_that_signed_the_existing_journal():
    anchor = LEDGER_SPEC.anchors["digicert"]

    assert (
        anchor.signer_certificate_sha256,
        anchor.signer_spki_sha256,
    ) == DIGICERT_JOURNAL_RESPONDER
    assert [
        (signer.certificate_sha256, signer.spki_sha256)
        for signer in anchor.additional_signers
    ] == [DIGICERT_2026_RESPONDER]


def test_digicert_2026_responder_receipt_verifies_under_production_pins():
    signed_at = verify_receipt(
        _probe_digest(),
        PROBE.with_suffix(".tsr"),
        "digicert",
        anchor_dir=PRODUCTION_ANCHORS,
        enforce_production_pins=True,
    )

    assert signed_at == datetime(2026, 9, 28, 18, 36, 12, tzinfo=timezone.utc)


def test_digicert_2026_responder_receipt_is_refused_without_its_pin():
    digicert = LEDGER_SPEC.anchors["digicert"]
    spec = dataclasses.replace(
        LEDGER_SPEC,
        anchors={
            **LEDGER_SPEC.anchors,
            "digicert": dataclasses.replace(digicert, additional_signers=()),
        },
    )

    with pytest.raises(ReleaseChainError, match=DIGICERT_2026_RESPONDER[0]):
        receipt_release_chain.verify_receipt(
            _probe_digest(),
            PROBE.with_suffix(".tsr"),
            "digicert",
            spec=spec,
            anchor_dir=PRODUCTION_ANCHORS,
            enforce_production_pins=True,
        )
