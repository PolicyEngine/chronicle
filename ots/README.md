# Bitcoin-anchored checkpoints (OpenTimestamps)

Every witnessed release manifest in `releases/manifests/` has a sibling proof
here: `ots/<stem>.json.ots` is an [OpenTimestamps](https://opentimestamps.org)
timestamp over the exact bytes of `releases/manifests/<stem>.json` — the same
bytes the two RFC 3161 authorities witness and the pinned producer key signs.

## What this adds

`releases/README.md` states the limit of the existing scheme: internal
verification proves a clone is self-consistent, but cannot by itself
distinguish the original history from a complete, freshly witnessed
replacement fork, so verifiers must retain an external checkpoint. These
proofs are that checkpoint, kept in a system the operator does not control.

A completed proof carries a Bitcoin block attestation: the manifest bytes
existed no later than that block's time. Because each manifest commits to the
full journal bytes (`state.jsonlSha256`, `state.lineCount`), the immutable
prefix (`state.immutablePrefixSha256`), and the previous manifest
(`previousManifestSha256`), one attestation bounds the existence time of the
whole journal state and manifest chain it commits to. A rewritten history
would need its own anchors, and Bitcoin will only ever attest the time the
replacement was actually made — backdating is not available to anyone,
including us.

The proofs do not add uniqueness: like the RFC 3161 receipts, they cannot
prove that no parallel fork exists, when GitHub accepted a proposal, or that
a manifest's claims are true. They move the anteriority bound outside the
operator's git history; the other caveats in `releases/README.md` stand.

Anchoring began 2026-08-19. Every release manifest that existed then,
releases 0000 through 0014, was stamped that day, so their Bitcoin bounds
start there; the RFC 3161 receipt times remain the earlier per-release
witnesses. Later manifests are stamped by the scheduled job soon after they
land.

## Verify

From a clone, first re-verify the witnessed chain (this recomputes the
journal digest that the head manifest commits to), then check any release's
proof against Bitcoin:

```console
python3 scripts/verify_release_chain.py --full
ots verify -f releases/manifests/<stem>.json ots/<stem>.json.ots
```

The `ots` command is the OpenTimestamps client
(`pip install opentimestamps-client`, or run it as
`uvx --from opentimestamps-client ots`). Full verification checks the
attested block header against a local Bitcoin node. Without a node, run

```console
ots --no-bitcoin verify -f releases/manifests/<stem>.json ots/<stem>.json.ots
```

which validates that the proof commits to the file's exact bytes and prints
the Bitcoin block height and merkle root to check against any block source
you trust. A proof whose attestation has not yet been aggregated into
Bitcoin reports `Pending confirmation in Bitcoin blockchain`; pending proofs
are upgraded in place by the scheduled job once the calendar's aggregate
transaction confirms.

To sweep every proof in the repository at once:

```console
python3 scripts/ots_anchor.py verify
```

This fails on any digest mismatch or missing proof, and with
`--require-bitcoin` also fails while any attestation is still pending.

## Operations

A scheduled GitHub Actions job (workflow on the default branch) checks out
the journal branch and runs `python scripts/ots_anchor.py run` daily: it
stamps any manifest that lacks a proof, tries to upgrade pending proofs, and
commits the result. The run is idempotent. Stamping happens on a temporary
copy so nothing is ever written under `releases/`, which the append gate
keeps closed to anything but exact release bundles. Once a proof carries a
Bitcoin attestation it is left untouched so its committed bytes stay stable;
`git log` retains every earlier pending version.
