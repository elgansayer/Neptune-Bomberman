# Factory intake and durable ownership

## Automatic preparation

[`provision.py`](PROVISIONING.md) installs/builds pinned Godot and Beetle Saturn
in a coordinator-owned cache, validates real capabilities, preserves receipts,
and rechecks/reuses healthy outputs. Run preparation in its network-enabled
sandbox before entering the offline verifier. Missing recipe/host dependency,
concurrent install, disk pressure and command failure are explicit resumable
outcomes. #518 / FACTORY-017 owns integration into the existing factory lifecycle
and extension to other required tools; the CLI alone does not enable that daemon.


## Research host preparation

[`host_readiness.py`](HOST_READINESS.md) (#25) prepares and audits the supplied
research VPS against the layout, account and limit requirements in
[REQUIREMENTS.md](../../docs/restart/REQUIREMENTS.md). The operator writes a
declaration of accounts, paths, credential files, concurrency and spend limits;
the tool then reports the host's OS, resources, running services, layout, private
input protection and credential separation against it. It never opens a
credential file, reads original media, calls a provider or GitHub, starts a
service or provisions anything, so a passing report is not credential validity,
media authenticity or factory health. Absent media and absent provider
credentials stay apart from installed software.

`host_backup.py` writes encrypted research/state archives and restores them in a
verified drill. The key never reaches argv or the environment, the archive is
authenticated before anything is decrypted, unsafe members are refused and every
restored file is checked against the archive's manifest. Original media is never
archived, and the off-host origin of a restored copy is an operator attestation
that the report records as unverified.

## Existing Repo Factory integration

`verify.py` is the local entrypoint for the existing Elgl Repo Factory's Neptune
verification planner. It imports the same classifier, command builder and result
validator as `tools/merge_gate/run.py`; it does not introduce another scheduler.

```sh
python3 tools/factory/verify.py --changed-path game_instance.gd \
  --toolchain .factory-tools/godot --evidence .godot/factory-verification/run-001
```

Repeat `--changed-path` for every changed file. Empty, malformed and unbounded
selections fail. Metadata, runner and gameplay selections require the same 5/8/10
checks as CI. An offline pinned Godot binary plus matching native addons is
required before any native selection executes; this command never provisions a
missing cache. The existing install helper may provision it on the coordinator
before entering the no-network verifier. Missing, failed, timed-out or incomplete
results fail; source changes during a run and stale evidence directories fail.

The coordinator owns a primary Git clone with `.git` inside that canonical root
and `.factory-tools/godot` below it. Worker worktrees must belong to that clone,
so their Git common directory remains accessible through the sandbox's read-only
canonical mount. The factory links the ignored `.factory-tools` cache into each
worktree, as it already links other dependency caches. Do not point a worker at an
unrelated canonical checkout or a cache symlink outside the restored roots.

The existing factory must run this command inside its hardened verification
namespace: host login homes, coordinator configuration/state, sibling workspaces
and runtime sockets hidden; only the task worktree writable, canonical dependencies
read-only, private temporary storage and loopback networking. The CLI alone is not
a sandbox. Its one structured receipt includes source identity, plan and every
literal successful command result; exit zero without that receipt is rejected by
the factory planner. This local report never impersonates required GitHub CI.

This preparatory integration does not enable the Neptune daemon profile. The
shared factory still rejects live `neptune` configuration until the separate
tests-only lifecycle/merge path is implemented. Elgl/workout reviews and running
services remain unchanged. One actual issue, quota/failure handling, restart
recovery and continuity still require #33 acceptance. Raw research inputs and
other projects' credentials must never be mounted into ordinary game workers.

## Requirements before preparation

Ask what a selection needs before provisioning or entering the offline verifier:

```sh
python3 tools/factory/verify.py --plan --changed-path README.md
python3 tools/factory/verify.py --plan --changed-path game_instance.gd --changed-path README.md
```

`--plan` takes only `--changed-path` (repeat it for every changed file) and rejects
`--toolchain` and `--evidence`. It reuses the CI classifier, so metadata, runner and
gameplay selections need exactly the 5/8/10 checks of a real run and of CI. It prints
one line, `NEPTUNE_FACTORY_REQUIREMENTS=` plus JSON with sorted keys, and exits 0.
Empty, malformed, unsafe or unbounded selections exit 1 with `FAIL:` on stderr and no
stdout. So does a runner or gameplay selection whose `tools/godot/toolchain.json` is
missing or invalid; a metadata selection never reads it. Usage errors exit 2.

Planning verifies, installs, downloads and executes nothing: no `git`, installer,
engine or check subprocess starts, no evidence or cache directory is created, and an
absent engine or cache is not an error. Without `--plan` nothing changes: the toolchain
and evidence arguments stay required, and a missing cache or failed check still fails.

| Field | Contract |
| --- | --- |
| `schema` | `neptune.factory-requirements.v1` |
| `scope` | Starts `requirements only`: no check ran and no host, tool cache or engine was inspected |
| `plan` | The shared classifier result: `mode` (`metadata`, `runner`, `gameplay`), sorted unique `paths` and the ordered `required` check names |
| `baseline.checks` | Required checks that need no engine: the core checks every selection runs |
| `baseline.python`, `baseline.executables` | Declared interpreter minimum and host tools those checks invoke (`cc`, `git`, `openssl`) |
| `native.required` | True for runner and gameplay selections: the test a real run applies before it demands the offline cache |
| `native.checks` | Required engine checks; `baseline.checks` then `native.checks` equals `plan.required` |
| `native.executables` | Host tools beyond the engine: `Xvfb` when `native-runtime` (a graphical client) is required, else empty |
| `native.toolchain` | `null` unless required. Otherwise the lock's pinned requirement: `tool` (`godot`, the `provision.py --tool` ID), `lock` path, `lock_sha256`, `godot_version`, `binary_name`, `binary_sha256` and `addons` (repository path to SHA-256) |

These are declared requirements, not observations. Nothing reports an installed
version, probe result, capability, Git identity or readiness, and the lock's download
location and every command are deliberately omitted. `native.required` and the
`executables` lists mean needed, not present. The result has a different prefix and
schema from the verification receipt and no `conclusion`, `identity` or check statuses,
so it cannot stand in for one. `native.toolchain.lock_sha256` equals
`offline_toolchain.lock_sha256` in the evidence `report.json` of a later real run on the
same checkout.

### Coordinator use

Candidate repository code is not host policy. `--plan` executes the `verify.py` and
classifier of the checkout that contains it and reads that checkout's toolchain lock,
and a worker can edit all three. The isolated coordinator therefore:

1. derives the changed-path list itself from the exact head/base diff, as the merge
   gate does, never from the worker's report, and binds the result to those commits.
   The result carries no Git identity;
2. runs `--plan` from its own trusted checkout of the protected base, not the task
   worktree, inside the credential-free no-network namespace. That checkout may be
   read-only because planning writes nothing;
3. uses the result only to reserve the shared slot and request preparation: it compares
   `baseline` and `native.executables` with host preflight and, for `native.toolchain.tool`,
   runs the trusted `provision.py` recipe. Provisioning reads the trusted revision's own
   lock. No value from the candidate tree, including a changed lock or hash, is passed to
   an installer or command;
4. runs the real command afterwards with `--toolchain` and `--evidence` and validates its
   `NEPTUNE_FACTORY_VERIFICATION=` receipt. A candidate that edits the planner, lock or
   provisioning files does not change what the coordinator prepared or trusted: its run
   fails closed on a cache that lacks the changed pin, and required GitHub CI remains
   authoritative;
5. never records the result as readiness, a capability, verification or CI.

## Tests-only GitHub handoff

The shared factory's Neptune GitHub adapter is tracked by #77. It reads the
required `Neptune merge gate` as a GitHub Actions app 15368 check-run for the
exact head, rather than accepting a same-name commit status. Missing checks
wait; skipped, neutral, failed, cancelled and timed-out required checks block.
It verifies that current protected main is contained in the candidate head.
Retarget stacked children to main after their parent merges and rerun checks.

The coordinator validates the existing strict branch protection, app identity,
zero required approvals, administrator enforcement and retained-branch settings.
Use native `--auto --merge --match-head-commit` for the tested head. GitHub's
atomic protection handles a head/base change after the coordinator's read.
Already-enabled auto-merge is reconciled without repeatedly re-enqueuing it.
No approving AI or human review is required for Neptune. Preserve other projects'
review policies when reusing their factory.

This boundary is separate from provider execution and daemon activation. A real
merge through the adapter demonstrates publication, not a complete AI job,
restart recovery or continuous operation. #33 still requires those live tests
before enabling unattended continuity.

## Named supplied-trace checks

Actual pinned original experiment recording and public-key authentication use
[`reference_receipt.py`](REFERENCE_RECEIPTS.md) (#579/#511). This separate trusted
coordinator entrypoint reuses the existing sandbox/host gate; supplied traces and
plausible hashes alone never establish source authenticity.

The opt-in #576/#76 contract runs the existing exact behaviour-trace comparator
in addition to the unchanged path-based checks. It uses the existing accepted
task's string fields, without another intake or receipt schema. The coordinator
adds the exact selector `check:behaviour-trace-exact-v1` to `task.acceptance`.
In `task.evidence`, it supplies exactly one of each of these five records:

```text
trace-v1:contract:<sha256 of canonical trace contract>
trace-v1:reference-source:<sha256 of canonical reference source object>
trace-v1:candidate-source:<sha256 of canonical candidate source object>
trace-v1:reference-file:<sha256 of raw reference.json bytes>
trace-v1:candidate-file:<sha256 of raw candidate.json bytes>
```

Canonical object bytes use `tools/saturn_lab/compare_trace.py:canonical` encoded
as UTF-8. The contract identifies the declared scenario, ruleset, observation
units, input recording and rational clock. Source objects retain the existing
build, content/input lock, capture and adapter identities; the required roles are
`reference` and `implementation`. Source object hashes may differ. The comparator
still requires an identical contract and exact ordered observations, with no
alignment, tolerance, dropped samples or relaxed assertions.

The coordinator captures and binds candidate artifacts after the relevant build
and capture step, before verification. Ordinary issue prose or a worker's claimed
hash must not establish those identities. These declarations are consistency
requirements, **not source authentication**. #511 must supply independently
authenticated original/candidate executions before any real fidelity claim.
The accepted intake remains subject to its existing freshness/revision/full-Git-
scope checks; replacing the task or artifacts invalidates the run.

Place the declared artifacts on a separate coordinator-supplied read-only mount:

```text
/private/supplied-artifacts/behaviour-trace-exact-v1/reference.json
/private/supplied-artifacts/behaviour-trace-exact-v1/candidate.json
```

```sh
python3 tools/factory/verify.py --changed-path docs/owned-result.md \
  --intake /private/accepted-task.json \
  --feature-artifacts /private/supplied-artifacts \
  --toolchain /prepared/godot --evidence /private/evidence/unique-run
```

The artifact mount must be outside candidate source and output evidence, without
symlink components. The CLI checks identities, bounded strict JSON and trace
semantics before baseline commands, then actually executes the comparator and
checks that the files remained unchanged. Unknown `check:` selectors and malformed,
duplicate, incomplete or orphaned `trace-v1:` requirements fail. Missing, replaced,
truncated, skipped-summary or mismatching artifacts cannot become a successful
feature result. Arbitrary commands from task strings are never executed.

The same `neptune.factory-verification.v1` receipt gains optional
`feature_requirements` and `feature_checks` objects. A feature result records the
actual in-process comparator operation/code identity, artifact identities and
existing comparison result, including first divergence. It is a supplied-observation
check, not proof that original Saturn or production Godot ran. Legacy selections
without the selector preserve their five/eight/ten checks and receipt fields.
`--plan` still reads no intake or artifacts and rejects this execution option.

This is a local verifier interface. The live shared Elgl adapter does not yet
select, mount or enforce these optional fields. Keep #76/#511 open until that
integration, authenticated private experiments and relevant mutation controls pass.
Neither ordinary green CI nor this supplied-artifact contract establishes the
whole game's state, native pixels or sample-timed audio parity.

## Local ownership foundations

Implements the local foundations of #71/#72. No scheduler, provider, remote GitHub
adapter or supervised VPS service is started by these tools. A green suite proves
these contracts; it does not close #33's live issue-to-merge/restart gate.

Run `python3 tools/factory/check.py`. Python 3.11+ and standard-library SQLite are
enough. Tests include two separate processes racing for a claim, a process killed
inside a database transaction, restart recovery, stale-worker mutation rejection,
and an ambiguous publication that must remain blocked.

## Trusted intake boundary

### Bind verification to the accepted task

The opt-in `verify.py --intake` path implements the bounded source-scope portion
of [#559](https://github.com/elgansayer/Neptune-Bomberman/issues/559) under #76.
It consumes the existing `neptune.factory-intake.v1` snapshot; no new intake
schema, scheduler or executable issue-text format is introduced.

```sh
python3 tools/factory/verify.py \
  --intake /private/fresh-task-intake.json \
  --changed-path tools/factory/example.py \
  --toolchain /canonical/repo/.factory-tools/godot \
  --evidence /private/verification/run-001
```

Repeat `--changed-path` for every actual changed file. The verifier reads the
complete committed diff from the snapshot's exact base to current HEAD, with
rename detection disabled so both old and new paths are checked. It requires
that base to be an ancestor, the selection to equal the full diff, each path to
be inside a literal accepted `task.scope.paths` boundary, and the number of paths
to stay within `max_files`. Empty diffs fail. A prefix such as `tools/factory2`
does not match an accepted `tools/factory` directory.

Tracked, staged and untracked source must be clean. Assume-unchanged and
skip-worktree index flags are rejected even on unselected files. Repository/index
override environment variables are rejected. Keep the immutable intake, tool
cache, logs and evidence outside candidate source or in explicitly ignored
directories. The verifier does not discard changes or reset index flags.

The snapshot must be a regular file of at most 256 KiB with unique JSON keys.
Existing readiness checks enforce its freshness, prerequisite attestations,
capabilities and active-work inventory. The coordinator supplies a fresh snapshot
after reconciling ownership; its admitted job is not an overlapping external
claim in that inventory. The snapshot is not proof of a live provider lease.
Expired/future/not-ready snapshots and a different repository fail. Verification
re-reads and revalidates the snapshot and candidate after all checks; a changed
task/revision, snapshot bytes, HEAD, diff or working source prevents success.

Opt-in reports and stdout receipts add `task_binding`: repository, issue, feature
ID, revision, complete task and raw-intake SHA-256, base/head and actual changed
paths. `identity` also records the accepted base. Existing path-only invocation,
its receipt shape and the shared 5/8/10 check plan remain unchanged. `--plan`
rejects `--intake` and remains requirements-only: it does not read Git or intake.
Upgrade the existing factory consumer deliberately before opting into the added
receipt fields; this CLI does not change a deployed coordinator.

The coordinator still owns trusted policy, Git configuration/metadata, task
revision and current-base selection. Run its trusted entrypoint in the existing
credential-free verifier sandbox, derive paths independently and validate the
returned binding against its accepted task and current protected branch. A
candidate must not choose a narrower task or verify itself using its own edited
policy. The local tool establishes consistency with supplied trusted intake;
it does not authenticate GitHub state or private reference captures.

Named native/browser/network/pack and exact state/pixel/audio acceptance contracts
remain #76/#511 integration work. Passing this source-scope guard alone cannot
establish an authentic reference experiment, Saturn parity or factory continuity.

`readiness.py` consumes a coordinator-produced snapshot. It never executes issue
text, model output or shell commands. The coordinator must obtain fresh issue/PR
state, authenticate dependency evidence and resolve the catalogue's feature IDs.
Schema validation cannot establish that a self-reported proof is true, that a
declared small scope is semantically small, or that a worker stayed within scope.
The later integration must compare changed files and actual tests to this contract.

Snapshot fields (all required):

| Field | Contract |
| --- | --- |
| `schema` | `neptune.factory-intake.v1` |
| `captured_at` | UTC Unix seconds; rejected after 900 seconds or if in the future |
| `base_sha` | Exact 40-character Git commit identity |
| `task` | The bounded task below |
| `available_capabilities` | Explicit list established by host preflight |
| `prerequisite_evidence` | Per-feature verified result with head/base, SHA-256 report and evidence reference; issue closure alone fails |
| `active_work` | Explicit PR/lease inventory with repository, issue, feature and literal scope paths |

Task fields: `repository`, positive `issue`, stable `feature_id`, `revision`
(SHA-256 of the trusted source issue/intake revision), `kind` (implementation,
research, verification or operations), `state=open`, nonempty `acceptance` and
`evidence` lists, `prerequisites` and `capabilities` lists, and `scope` containing
one observable `goal`, literal relative `paths` and `max_files` between 1 and 20.
An epic is rejected. Directory overlap is component-aware. Expired external claims
remain conflicts until the coordinator establishes what happened to their worker.

```sh
python3 tools/factory/cli.py readiness /private/intake.json
python3 tools/factory/cli.py enqueue --database /private/jobs.sqlite /private/intake.json
python3 tools/factory/cli.py show --database /private/jobs.sqlite example/game:FACTORY-001
python3 tools/factory/cli.py recover --database /private/jobs.sqlite
```

These commands do not contact GitHub. Missing parent directories and malformed,
stale or incomplete snapshots fail. Refreshing unchanged intake does not revive a
cancelled/submitted job. Changed issue revisions need deliberate reconciliation;
they cannot silently replace an active contract. The snapshot refresh must itself
reflect fresh external claims, dependencies and capabilities.

## Coordinator API

`JobStore(database_path)` exposes `enqueue`, `claim`, `heartbeat`, `checkpoint`, `record_attempt`, `attempts`,
`request`, `deliver`, `status`, `begin_publication`, `release`, `cancel`, `recover`, `reconcile` and `get`.
Close connections explicitly. Use an existing private coordinator-owned directory
on local disk; SQLite on a shared network filesystem is not supported here.

Each successful claim returns an owner, opaque token, increasing fencing epoch,
task digest, expiry, exact base and saved checkpoint. Every worker mutation checks
the live receipt in an immediate SQLite transaction. The database and audit events
survive coordinator restart. Failed transactions roll back. Backwards clock steps
fail closed instead of extending ownership invisibly. Deploy with a reliable host
clock; do not supply a worker-controlled clock or database path.

Checkpoint payloads require exact base/head and the next step, with a 64KiB cap.
Store large logs separately and retain their evidence references. Expired ordinary
claims can be reclaimed with a new epoch; stale receipts cannot mutate state.
Jobs in the same repository also reserve overlapping declared paths.

Publication is a separate boundary. Record immutable branch/head/base intent
before any remote effect. If a worker dies while publishing, recovery blocks the
job and retains its scope reservation. Cancellation also retains an existing
publication hold. The trusted coordinator checks GitHub and stops any old publisher
before calling `reconcile(..., 'clear', evidence_ref)`; a confirmed existing PR
must be resumed rather than duplicated. A submitted PR is not a merged result.

**Fencing is enforced at this local API boundary.** A future publication adapter
must be the sole holder of remote publish/merge credentials and honour the same
receipt. A token cannot prevent an independently credentialled stale process from
calling GitHub directly. `reconcile(..., 'accepted', ...)` trusts its caller's
external verification; it does not inspect checks/ancestry itself. Keep worker
processes away from the coordinator database and these privileged operations.

### Ownership status

```sh
python3 tools/factory/cli.py status --database /private/coordinator/jobs.sqlite
```

`status()` (schema `neptune.factory-status.v1`) lists every job's state, owner,
epoch, reason, declared scope, checkpoint presence/head/next step, open requests
and, for ready jobs, the current admission reasons, such as a stale snapshot, a
reserved overlapping scope or the running cap. It never returns tokens and writes
nothing. `lease.recorded` describes the store's own lease only.
`process_liveness` is always `unknown`, because the store cannot observe processes.
A session outside this store and the shared broker remains unaccounted. Pass
`JobStore(path, max_running=N)` to queue claims beyond a configured cap.

### Durable attempts, spend and provider failure policy (#33)

`record_attempt(receipt, outcome, provider, model, spend=0, reason="",
retry_after=None)` persists one provider attempt and its consumed budget. The
outcome is `succeeded`, `timeout`, `quota` or `failed`; provider/model version,
attempt number, spend and history survive coordinator restart. A success keeps
the lease, resets the consecutive-failure count and never marks the job submitted
or merged.

A timeout, quota response or failure releases the lease at a new epoch and
returns the job to `ready` with `next_eligible` set. That delay is exponential
from the configured base, if supplied by the provider, or `retry_after`,
capped by `max_backoff`. Claims refuse the job until the delay passes, so a
transient provider fault cannot cause an immediate retry loop. After
`max_attempts` consecutive failures the circuit opens: the job becomes `blocked`
with no next-eligible time and cannot be reclaimed until the coordinator calls
`reconcile(..., 'clear', ...)`, which resets only the consecutive-failure count
and retains attempt/spend history. A failure never produces false completion or
a publication intent.

`spend_limit` is optional at construction and defaults to `None`; this module
invents no spending limit. When set, a job whose persisted spend reaches the
limit cannot be claimed, and `status()` reports it as blocked admission while
preserving evidence. `max_attempts` (default 3), `backoff` (30) and `max_backoff`
(3600) are bounded retry defaults, not spending policy.

`status()` exposes per-job `attempts`, `failures`, `provider`, `model`, `spent`
and `next_eligible`, plus the configured `limits`. `attempts(job)` lists the
persisted history. Events `attempt`, `attempt_failed` and `circuit_opened`
record every outcome. The CLI mirrors this: `cli.py attempt --receipt ...
payload.json` records an attempt, and `cli.py history --database ... <job>`
prints its history. Any non-running outcome deletes the released receipt.

### Bounded experiment requests and results (#779)

A worker holding a lease on a dependent job asks another job's owner for at most
eight bounded experiments:

```python
store.request(receipt, [{"producer": "owner/repo:CODE-001",
    "question": "Which caller reaches the resume path?",
    "binding": {"release": ..., "module_sha256": ..., "cpu": ...,
                "address_space": ..., "load_lifetime": ...},
    "verified": ["original-bytes"]}])
```

The request records the producer's current task digest. The dependent's lease
is released at a new epoch and the job enters `waiting`, keeping its checkpoint.
Repeating an identical request is idempotent. Repeating an already fulfilled
request returns its result instead of dispatching it again. The producer's claim
receipt lists only open requests from dependents that are not cancelled.

`deliver(receipt, request, result)` requires the producer's live receipt. The
result names `task_digest`, `base_sha`, `head_sha`, `report_sha256`, `evidence_ref`,
`status`, `binding`, `verified` and `hypotheses`, and must match all of these:

- the task digest recorded at request time;
- the exact requested source binding;
- the producer's current checkpoint head and base.

Otherwise the call fails. A failed or truncated result, or one missing a
requested verification kind, is recorded as `result_rejected`, and the request
stays open. Hypotheses are retained beside the result but never count as
`original-bytes` or `natural-runtime` verification.

The first matching verified result fulfils the request. When a dependent's last
open request is fulfilled, the dependent returns to `ready` exactly once. Its
next claim receipt carries the saved checkpoint and the selected result metadata.
Re-delivering the identical result is harmless; a different result is rejected.

These are local consistency checks, not source authentication. The trusted
coordinator must bind the reported hashes to retained private evidence before
calling `deliver`.

The coordinator can drive the same API without custom code. Receipts live only
in coordinator-held files, never in stdout or worker workspaces:

```sh
F="python3 tools/factory/cli.py"; D="--database /private/coordinator/jobs.sqlite"
$F claim $D --owner claude --receipt /private/leases/779.json owner/repo:FACTORY-020
$F checkpoint $D --receipt /private/leases/779.json checkpoint.json
$F request $D --receipt /private/leases/779.json requests.json   # JSON list of specs
$F claim $D --owner codex --receipt /private/leases/707.json owner/repo:CODE-001
$F deliver $D --receipt /private/leases/707.json --request <id> result.json
$F release $D --receipt /private/leases/707.json --state ready --reason "probe done"
```

`claim` creates its receipt file exclusively with mode 0600 before it takes the
lease. It refuses an existing path and removes the file if the claim fails. The
file is deleted when `release` ends the lease, or when `request` moves the job to
`waiting`. A copy kept elsewhere is refused as stale.

## Next integration on the VPS

1. Inspect active jobs and use an isolated Neptune state/workspace directory.
2. #73: build a dependency-aware selector and fresh GitHub intake adapter; reuse
   the existing catalogue validator for cycles. Skip blocked reference jobs while
   original gameplay/tooling work remains ready.
3. #74/#75: isolated workspaces and observed tool/input capability checks.
4. Attach the existing supported VPS Codex worker, or a configured OpenHands
   adapter. Keep one implementation job active initially. Provider policy and
   spending limits belong to configuration; this module invents none.
5. #77: reconcile current head/base/checks and remote publication intents with
   the existing tests-gated merger. Preserve zero required approving reviews.
6. #33: execute one actual job, interrupt/restart, reconcile and complete it;
   automatically select the next job. Only then supervise continuous operation.

Back up the database with SQLite's backup API (or a correctly quiesced snapshot),
not by copying only the main file while WAL writes continue. Test restoration and
reconcile remote state before permitting publication after a restore.

## Manual sessions and the supervised canary

An outside-protocol manual Codex, Claude, Gemini or OpenCode session is counted
in shared provider capacity once it is enrolled with
`repo-factory sessions enrol --provider <codex|claude|google|opencode> --pid <PID> --label <name>`
(Elgl #9827). It runs as a guardian: it holds one renewable slot under the
router's own provider limit while that exact process (PID plus start time) lives,
and releases the slot when the process exits or on a signal. It never signals or
adopts the participant.

`repo-factory sessions audit` reports enrolled sessions as
`live_recorded_guardian_and_lease`. An unenrolled session remains unaccounted,
and an audit never proves account-wide coverage.

One supervised Neptune canary step is
`repo-factory task run --issue <N> --supervised-session`, run as the service
user with the Neptune instance environment. Each call advances one durable
checkpoint and never enables continuity. Continuity stays disabled until #33
accepts it.

A coordinator can request bounded experiments between jobs with
`tools/factory/cli.py request` and `tools/factory/cli.py deliver` (#781/#782).
Only a result bound to the task digest, the source binding and the checkpointed
head unblocks the dependent, exactly once.
