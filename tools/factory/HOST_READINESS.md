# Research host preparation and readiness

Operator tooling for #25. It prepares and audits the supplied research VPS against
the layout, account and limit requirements in
[REQUIREMENTS.md](../../docs/restart/REQUIREMENTS.md). It purchases nothing, starts
no service, opens no credential file, calls no provider and GitHub, and reads no
original media. It exists so that host preparation is a declared, checkable state
instead of an operator's memory.

| Tool | Purpose |
| --- | --- |
| `host_contract.py` | The declaration schema and the receipt contracts both tools read |
| `host_readiness.py` | A redacted static report of this host against a declaration |
| `host_backup.py` | Encrypted research/state backups and restore drills |

The declaration is written on the host by the operator. It names accounts, paths
and explicit limits. It never carries a secret value, a command or free text, so
nothing in it can be echoed into a report or an issue as a credential.

## Operator order

```sh
python3 tools/factory/host_readiness.py template > /private/coordinator/host-declaration.json
# edit the declaration, then:
python3 tools/factory/host_readiness.py report --declaration /private/coordinator/host-declaration.json \
  --output /private/evidence/host-readiness-001.json --strict
```

`--strict` exits nonzero while any static check blocks. The report is written to a
new file; existing evidence is never overwritten.

1. **Accounts and layout.** Create the coordinator and worker accounts as
   separate non-root users, and the `repos`, `state`, `workspaces` and
   `private/*` directories of the REQUIREMENTS.md layout. `repos` and `state`
   belong to the coordinator; `workspaces` belongs to a non-root role account.
2. **Declaration.** Fill in `roles`, `directories`, `inputs`, `credentials`,
   `policy`, `backup` and `services`. Every unknown field, duplicate path,
   overlapping layout and out-of-range limit is rejected rather than defaulted.
   A limit that is not configured stays null and is reported as absent, so an
   unedited template grants no concurrency and no spend.
3. **Report.** Run the report as the coordinator account and fix every blocking
   check. Keep the resulting JSON with the issue evidence.
4. **Credentials.** Provision the declared credential files on the host over a
   secure channel, owner-only (`0600`) inside a directory that is not writable by
   group or other. The tools only `lstat` them.
5. **Backup.** Take an encrypted archive, copy it to the off-host destination and
   restore it from that copy with a drill.

## Layout, accounts and read-only media

The report checks these properties, so create them exactly as stated:

| Object | Required state |
| --- | --- |
| coordinator account | Non-root and a different account from the worker. It may hold administrative groups; it owns `repos` and `state` |
| worker account | Non-root, in no privileged group (`root`, `sudo`, `wheel`, `docker`, `podman`, `lxd`, `disk`, `shadow`, `adm`) and unable to reach a container-control socket |
| `repos`, `state` | Real directories, no world access, owned by the coordinator. The worker must not be able to write `repos` or read `state` |
| `workspaces` | A real directory owned by a non-root role account, with no world access |
| `private/*` inputs | Real directories owned by the coordinator or root, no world access, unreachable by the worker |
| original media | A dedicated read-only mount covering the input directory, with no symlink inside it |

Mount the supplied media read-only on its own mount point rather than leaving it
in a writable directory, for example a bind mount of the disc directory:

```text
/srv/neptune/private/media/disc  /srv/neptune/private/disc  none  ro,nosuid,nodev,noexec,bind  0  0
```

A dedicated mount whose superblock is read-only satisfies the same check, so an
image mounted `ro` from its own filesystem is equally acceptable. A read-only
root filesystem does not: the check requires a dedicated mount, not the
filesystem that holds everything.

A media input may instead declare `permissions` enforcement. Then the report
requires that no entry below the input carries a write bit. In both modes a
symlink inside a media input is reported, because it could point outside the
read-only input. That is weaker than a read-only mount, and the declaration
records which one was chosen.

Credential files belong to their role account, are `0600`, and sit in a
directory that is not writable by group or other. A credential inside a
repository, a workspace or the worker's home directory is reported as
misconfigured, because a worker could read or replace it.

## The declaration

```text
schema        neptune.factory-host-declaration.v1
root          absolute path of the research root, never a symlink
roles         coordinator and worker Unix account names
directories   repos, state and workspaces, relative to root
inputs        1..32 private input directories with kind, enforcement and need
credentials  credential files with role, kind, path and need
policy        max_concurrent_jobs, max_concurrent_heavy_jobs and the spend cap
backup        archive directory, drill receipt, sources, key and maximum age
services      the unit-name patterns the operator wants reported by name
```

| Field | Contract |
| --- | --- |
| `roles.*` | A Unix account name or null. The report checks that the two accounts differ, that neither is root and that the worker holds no privileged group or container-control socket |
| `directories.*` | Distinct relative paths that cannot overlap an input directory, so a worker cannot reach private inputs through the layout |
| `inputs.*.kind` | `media` for original discs, BIOS and the pinned Power release; `private` for emulator builds, settings, manifests and captures |
| `inputs.*.enforcement` | `media` needs `mount` (a dedicated read-only mount) or `permissions` (no write bits, no symlinks); `private` has none |
| `credentials.*` | One file per credential, owned by its role account, outside every repository, workspace and worker home. A worker credential and a coordinator credential may not be the same file |
| `policy.max_concurrent_jobs` | 1..64 or null. Null means "not configured", and the report says so |
| `policy.max_concurrent_heavy_jobs` | 1..64, never above the total job limit |
| `policy.spend` | `currency`, `daily_cap`, `monthly_cap` and `paid_fallback_allowed`. The daily cap may not exceed the monthly cap; any field may be null |
| `backup.sources` | Relative paths of the research state to archive. Original media, repositories and workspaces are refused, and a source may not contain a credential file |
| `backup.max_age_seconds` | 1 hour..1 year. Without it the report cannot judge archive freshness and says `indeterminate` |
| `services.watch` | At most 32 unit-name patterns. Only matching unit names appear in the report |

## The readiness report

Schema `neptune.factory-host-readiness.v1`. It records the OS, architecture,
kernel, CPU and memory, the filesystems that hold the declared paths, the running
service inventory, and one status per check.

| Status | Meaning |
| --- | --- |
| `ok` | The check passed on this host |
| `absent` | A declared prerequisite is not provisioned |
| `misconfigured` | The provisioned state contradicts the declaration |
| `indeterminate` | A probe could not establish the fact, so the check blocks like a wrong fact |
| `present-unverified` | Statically sound, but only a live call could confirm it |
| `not-applicable` | The related object is absent, so the check does not apply |

`summary.static_checks` is `pass` only when no non-optional check blocks.
`summary.absent_by_category` keeps absent media and absent provider credentials
apart from installed software, and `summary.installed_software` lists only what a
version probe found. Each capability (`saturn-experiments`, `provider-jobs`,
`backup`, `offline-verification`, ...) is `blocked` or `static-checks-pass`
according to the checks that serve it, so missing Saturn media blocks Saturn
experiments only.

The report establishes what the host looks like. It never establishes:

- credential validity, scopes, billing or quota;
- that the coordinator enforces the declared concurrency and spend limits;
- that any original media matches the accepted input locks (#26);
- that an off-host destination exists, is reachable or is independent;
- tool function beyond a version probe;
- factory health, which stays `not-assessed`.

No credential file is opened, no media byte is read and no environment variable
of the calling shell is passed to a child process. Report content is limited to
declared paths, counts, modes, owners and versions. The host identity is a
one-way hash of the machine id, never the hostname, the address or the raw id.

## Encrypted backups and restore drills

```sh
python3 tools/factory/host_backup.py keygen --declaration /private/coordinator/host-declaration.json
python3 tools/factory/host_backup.py create --declaration /private/coordinator/host-declaration.json
# copy the archive and its .json record to the off-host destination, then fetch them back
python3 tools/factory/host_backup.py restore-drill --declaration /private/coordinator/host-declaration.json \
  --archive /private/evidence/fetched/nbk-20261105T120000Z-1a2b3c4d.nbk \
  --sidecar /private/evidence/fetched/nbk-20261105T120000Z-1a2b3c4d.json \
  --into /private/evidence/restore-drill-001 --origin offhost
```

An archive is a tar stream of the declared sources plus a trailing manifest of
SHA-256 hashes, encrypted with AES-256-CTR by the host's OpenSSL and authenticated
with HMAC-SHA256 (encrypt-then-MAC). The cipher passphrase and the MAC key are
derived through HKDF-SHA256 from the random key file and a per-archive salt, so
no key material reaches argv or the environment; the passphrase travels over an
inherited pipe. The archive starts with the `NEPTUNE-NBK1` header and its own
salt.

The key is a 0600 regular file owned by the running account inside a directory
that is not writable by group or other. An existing key is never replaced.
Original media is never archived: keep disc fingerprints in the manifests and
record the archive's own hashes instead.

`create` writes the archive and a `neptune.backup-archive.v1` record beside it.
The record holds the archive hash and size, the manifest hash, the file and
directory counts, the declared sources, the key fingerprint and the host
identity. The archive directory is created owner-only.

`restore-drill` verifies the record against the archive, authenticates the whole
file before decrypting anything, rejects unsafe archive members, checks every
file against the manifest and runs an integrity check on every restored database.
It then writes a `neptune.backup-restore-drill.v1` receipt with the verified
counts and the origin of the restored copy.

`--origin offhost` is an operator attestation that this copy was fetched from the
off-host destination; the tool cannot observe it. `--origin local` marks a drill
that restored a copy already on this host, and the report then records the
off-host requirement as unmet. `independent_host` in the receipt compares the
source and restore host identities: equal identities mean the drill did not
demonstrate independent-host recovery.

## What this does not close

These tools prepare and audit a host; they do not provision one. The operator
still supplies the VPS access, the media, the credentials and the off-host
destination, and still runs the steps above on that host. A green test suite
here proves the tools' behaviour on a synthetic tree, not that a real host was
prepared. #25 stays open until the real readiness report and a real off-host
restore exist, and #26 still needs the actual supplied media.
