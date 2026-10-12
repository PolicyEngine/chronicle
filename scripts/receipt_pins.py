"""Consumer-owned trust and append-gate configuration for receipt."""

from __future__ import annotations

import pathlib

from receipt.append_gate import AppendGateSpec
from receipt.release_chain import AnchorSpec, ChainSpec, PinnedSigner


LEDGER_SPEC = ChainSpec(
    manifest_relative=pathlib.PurePosixPath("releases/manifests"),
    state_relative=pathlib.PurePosixPath("ledger/official_observations.jsonl"),
    prefix_relative=pathlib.PurePosixPath("ledger/immutable_prefix.json"),
    anchor_relative=pathlib.PurePosixPath("releases/anchors"),
    release_root_relative=pathlib.PurePosixPath("releases"),
    schema_version="thesis_ledger_release_v1",
    producer_public_key_filename="producer-ed25519.pub",
    producer_spki_sha256=(
        "4a90eff40455ce0d853d4bab1608efbdae1efaf8c06054ead6e396c5b0c4846e"
    ),
    anchors={
        "freetsa": AnchorSpec(
            filename="freetsa-root-2016.pem",
            pem_sha256=(
                "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"
            ),
            policy_oid="1.2.3.4.1",
            signer_certificate_sha256=(
                "32e841a95cc1164101ffde41298ef2fc75c1c4372ef095e88a6bbd47dfb191fc"
            ),
            signer_spki_sha256=(
                "fa02bd555e3e483d62b4e70be6218692068d2b0b0a7525db58dcbf2901cdb072"
            ),
        ),
        "digicert": AnchorSpec(
            filename="digicert-trusted-root-g4.pem",
            pem_sha256=(
                "ce7d6b44f5d510391be98c8d76b18709400a30cd87659bfebe1c6f97ff5181ee"
            ),
            policy_oid="2.16.840.1.114412.7.1",
            signer_certificate_sha256=(
                "4aa03fa22cd75c84c55c938f828e676b9caecab33fe36d269aa334f146110a33"
            ),
            signer_spki_sha256=(
                "7abda95ed7301ac94bded350babc319903d0b4f16c4e7e39346dba5f9e992b72"
            ),
            # DigiCert moved timestamp.digicert.com to a new responder under the
            # same pinned root in early September 2026. Releases 0000 to 0020
            # carry receipts from the responder pinned above, so both are pinned.
            # "DigiCert SHA256 RSA4096 Timestamp Responder 2026 1", serial
            # 084FDC334F7E454EDBC30F8FF9921835, issued by "DigiCert Trusted G4
            # TimeStamping RSA4096 SHA256 2025 CA1", valid 2026-08-05 to
            # 2037-11-04, extended key usage Time Stamping (critical). The
            # digests match the receipt the gate refused on 2026-09-27
            # (0021-a49e4e1aa0f35949.digicert.tsr) and a receipt fetched
            # independently on 2026-09-28 (tests/fixtures/production_tsa); both
            # verify under the pinned root at their own signing time. The
            # thesis repository pins the same responder (ThesisInstitute/thesis#255).
            additional_signers=(
                PinnedSigner(
                    certificate_sha256=(
                        "2da09da7f4131f9fe72db6c5e6e9c9656755af043f1ea742cc0d2120e141ebfc"
                    ),
                    spki_sha256=(
                        "753596b60a629061144cbd312017bbfb77510eac20b7eadc5fafb7cabe142fd5"
                    ),
                ),
            ),
        ),
    },
)


APPEND_GATE_SPEC = AppendGateSpec(
    chain=LEDGER_SPEC,
    prefix_schema_version="thesis_facts_immutable_prefix_v1",
    release_manifest_prefix="releases/manifests/",
    genesis_support_files=frozenset(
        {
            "releases/README.md",
            *(
                f"releases/anchors/{anchor.filename}"
                for anchor in LEDGER_SPEC.anchors.values()
            ),
            (f"releases/anchors/{LEDGER_SPEC.producer_public_key_filename}"),
        }
    ),
    # Every file in the judging (base) checkout that can decide a verdict. A
    # proposal that changes one of them together with the ledger is refused as
    # mixed, and a proposal that changes only these is reported by name.
    gate_surface=frozenset(
        {
            # The judge runs scripts/check_thesis_facts_append.py, so scripts/
            # is sys.path[0], and both pull request jobs also put it on
            # PYTHONPATH. Any file there can decide the verdict: these pins,
            # a module that shadows an import (the standard library's
            # included), or a sitecustomize.py, which runs at startup.
            "scripts/**",
            ".github/workflows/thesis-facts-append.yml",
            # `uv sync --locked --no-dev --project <base>` builds the judge's
            # environment from these, including the receipt version that
            # implements the gate. uv also reads the project's uv.toml and
            # .python-version, and reuses a .venv it finds there.
            "pyproject.toml",
            "uv.lock",
            "uv.toml",
            ".python-version",
            ".venv/**",
            "releases/anchors/**",
        }
    ),
    data_surface=frozenset(
        {
            "ledger/**",
            "releases/manifests/**",
        }
    ),
    assertion_content_keys=(
        "source_record_id",
        "value",
        "observed_at",
        "period",
        "geography",
        "entity",
        "aggregation",
        "filters",
        "domain",
    ),
)
