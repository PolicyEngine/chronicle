# Bitcoin checkpoints for the witnessed journal

This directory contains [OpenTimestamps](https://opentimestamps.org) proofs for
release manifests on the `codex/thesis-ledger-facts` journal branch. For a stem
`<stem>`, `ots/<stem>.json.ots` commits to the exact bytes of
`releases/manifests/<stem>.json` in a journal checkout. Those are the same bytes
witnessed by the release's two RFC 3161 authorities and signed by its pinned
producer key.

## What a proof establishes

A proof with a Bitcoin block attestation establishes that the manifest bytes
existed no later than that block. Each manifest commits to the full journal
bytes (`state.jsonlSha256` and `state.lineCount`), the immutable prefix, and the
previous manifest. An attestation therefore bounds the existence time of that
journal state and the manifest chain it incorporates without trusting this
repository's Git history as the only checkpoint.

The proof does not establish that the manifest's claims are true, that GitHub
accepted a proposal at a particular time, or that no parallel fork exists. A
rewritten history can acquire new anchors, but Bitcoin exposes the later time at
which those replacement bytes first existed; it cannot be backdated.

As of 2026-09-02 this directory carries 20 proofs, one per release 0000–0019,
and every proof is committed whatever its state. The proofs for releases
0000–0014 were first stamped on 2026-08-19 and already contain Bitcoin block
attestations. The proofs for releases 0015–0019 were stamped on 2026-09-02 and
are committed while still pending: each holds only calendar commitments until
the workflow upgrades it in place. The daily workflow stamps later manifests
after they appear and upgrades pending proof files when calendar attestations
can be folded into the serialized proof.

## Verify

Check a proof against a real checkout of the journal branch:

```console
ots --no-bitcoin verify \
  -f <journal-checkout>/releases/manifests/<stem>.json \
  ots/<stem>.json.ots
```

The workflow pins the client as
`uvx --from opentimestamps-client==0.7.2 ots`; use that invocation in place of
`ots` for the same reproducible client version. `--no-bitcoin` verifies that the
proof commits to the manifest's exact bytes and, when available, prints a block
height and merkle root for manual checking against a Bitcoin source you trust.

To sweep every manifest in a journal checkout against this proof tree:

```console
python3 scripts/ots_anchor.py verify \
  --manifests <journal-checkout>/releases/manifests \
  --ots-bin "uvx --from opentimestamps-client==0.7.2 ots"
```

This is strict: a mismatched or missing proof fails, and every manifest is
reported rather than only the first failure. Add `--require-bitcoin` to also
fail while any committed proof file still contains only pending calendar
attestations. `status` distinguishes that local serialized state from an
attestation a calendar may resolve in memory during verification.

The script establishes the binding without calendar traffic: the
`File sha256 hash` that `ots info` reads out of the proof must equal the
manifest's SHA-256. It then runs the client's own `--no-bitcoin verify` as an
independent check and echoes that output into the log. The client's verify path
first asks each calendar for upgrades, so for a pending proof the log carries
lines such as `Got 1 attestation(s) from <url>`, `Calendar <url>: Pending
confirmation in Bitcoin blockchain`, or `Calendar <url>: <error>` after a
transient failure. None of that is interpreted. Only the client's exact
`File does not match original!` line, or an exit status the client never uses,
fails a proof.

## Why proofs and automation live on `main`

The journal's `releases/` history is immutable, and its append gate admits only
complete release bundles. OpenTimestamps proofs are operational artifacts:
stamping creates them after a release exists, and upgrading rewrites them as
calendar transactions confirm. They therefore cannot live under `releases/`.

Keeping the proof tree, anchoring script, tests, and scheduled workflow together
on `main` keeps the trusted code and the mutable proofs in one place. The
workflow runs `main`'s script against a separate, shallow journal checkout that
has no persisted credential. It runs `run`, `verify`, and `guard`, stages only
`ots/`, and refuses a dirty worktree or a committed path outside `ots/` before
it pushes the proof-only commit directly to `main` with a plain, non-force
`git push origin HEAD:main`.

A non-fast-forward rejection starts a bounded retry: fetch and rebase onto the
new `origin/main`, refresh the credential-free journal checkout, rerun `run`,
`verify`, and `guard`, then recommit and retry. The workflow makes at most three
non-force push attempts and never pushes the journal branch.

## What the `ots/`-only guard does and does not provide

`main` is not protected. When the workflow was written (2026-09-02) the
repository API reported no rulesets, required checks, review requirements, or
push restrictions on `main`, and the direct push depends on that absence. The
workflow logs the current rule evidence at the start of every run, so a later
change shows up in the job log.

The `guard` subcommand and the workflow's `assert_commit_scope` run client-side,
in the same job that holds the `contents: write` token. They bound what a
correctly functioning run can publish: a stray file, an unexpected edit, or a
dirty worktree stops the push. They are not a server-side control. A compromised
job, a malicious dependency pulled in by the pinned client, or anyone else with
push access to `main` is not constrained by them. A repository ruleset that
protects `main` and lists this workflow as a bypass actor would add the
server-side boundary this design does not provide.
