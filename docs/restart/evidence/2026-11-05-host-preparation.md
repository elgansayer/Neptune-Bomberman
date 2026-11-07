# Research host preparation tooling, 5 November 2026

Scope: #25, "Provision isolated research host and operator prerequisites". This
change adds the declared, checkable mechanism for that issue. It does not claim
that a research host was provisioned, that media were supplied or that a factory
job ran. The supplied VPS was not reachable from the session that produced this
change: no SSH access, no media and no off-host destination were available, so
every host step below remains an operator action on the real host.

## Implemented

- `tools/factory/host_contract.py` defines the operator declaration
  (`neptune.factory-host-declaration.v1`) and the receipt contracts for the
  archive and the restore drill. The declaration names accounts, paths,
  credential files, concurrency and spend limits and never carries a secret
  value, a command or free text. Unknown fields, duplicate paths, an
  overlapping layout, an out-of-range limit and an unconfigured limit are
  rejected or reported as absent rather than defaulted.
- `tools/factory/host_readiness.py` produces a redacted static report
  (`neptune.factory-host-readiness.v1`) of a host against that declaration: OS,
  architecture, kernel, CPU, memory, the filesystems holding the declared paths,
  the running service inventory, the layout and account isolation, private
  input protection, credential separation, the declared policy limits and the
  backup configuration with its latest archive and drill. It opens no
  credential file, reads no media byte, calls no provider or GitHub and starts
  no job, so `absent` media and `absent` provider credentials stay apart from
  installed software, and `factory_health` stays `not-assessed`.
- `tools/factory/host_backup.py` writes encrypted research/state archives and
  restores them in a verified drill. The archive is a tar stream plus a
  SHA-256 manifest, encrypted with AES-256-CTR by the host's OpenSSL and
  authenticated with HMAC-SHA256 (encrypt-then-MAC). The cipher passphrase and
  the MAC key are derived through HKDF-SHA256 from a random key file and a
  per-archive salt, so no key material reaches argv or the environment. The
  restore authenticates the whole file before decrypting anything, refuses
  unsafe members, checks every file against the manifest and runs an integrity
  check on every restored database. Original media is never archived.
- `tools/factory/HOST_READINESS.md` documents the operator order, the
  declaration fields, the required layout, account and read-only media
  properties, the report's status vocabulary and what a report never
  establishes, and the backup and drill commands.
- `tools/factory/README.md` and `docs/restart/REQUIREMENTS.md` point at that
  document from the automatic-preparation and requirements pages.

## Actual commands and results

The suite for the changed area, from the repository root:

```sh
python3 tools/factory/check.py
```

```text
Ran 308 tests in 14.820s

OK
```

It includes the new `tools/factory/tests/test_host_backup.py` (25 cases) and
the corrected `tools/factory/tests/test_host_readiness.py` (42 cases). The
backup cases cover the RFC 5869 HKDF vector, the create/restore/drill round
trip, a restored database's contents, tampered ciphertext, a wrong key, a
truncated or foreign file, an archive that differs from its record, unsafe and
symlink archive members, a used or symlinked restore directory, a missing
source, a symlink or special file in a source, an unsafe key file, a keygen that
never replaces an existing key, and the absence of any key material in argv or
the environment.

The report was also executed against a real Linux host, the factory provider
sandbox container, with the unedited template declaration:

```sh
python3 tools/factory/host_readiness.py template > /tmp/opencode/declaration-template.json
python3 tools/factory/host_readiness.py report --declaration /tmp/opencode/declaration-template.json \
  --output /tmp/opencode/report-final.json
```

```text
{"report": "/tmp/opencode/report-final.json", "static_checks": "fail", "blocking": 25}
```

```text
schema             neptune.factory-host-readiness.v1
tool_sha256        ee4ec6830e264f861adce4e2d26c55f2e6d3e878ec3abd5b9bc4323ed8d52dbe
declaration_sha256 a1905a2a06b76d73bd3656f5c38723edd9323b91ac29e6a3ad11de01af524cb0
host               Debian GNU/Linux 13 (trixie), x86_64, 4 logical CPUs, 8134737920 bytes RAM
counts             absent 25, indeterminate 2, not-applicable 7, ok 9
absent by category backup 4, credential 5, identity 2, input 7, layout 4, policy 2, software 1
installed software c++, cc, docker, git, make, openssl, python3, rclone, rsync, ssh
```

That host has no `/srv/neptune` layout, no role accounts, no media and no
credentials, so every declared prerequisite is reported absent and the report
fails its static checks. It demonstrates the tool runs on a real host and
separates absent inputs from installed software. It is not the research VPS and
proves nothing about it.

The three tools are hashed into every report, archive record and drill receipt
through `tool_sha256`, so a later run against a changed tool is distinguishable.

## Honest limits

- No research host was provisioned, no account was created, no credential was
  issued, no media was mounted and no off-host destination was configured in
  this change. The operator still supplies the VPS access, the media, the
  credentials and the off-host destination, and still runs the documented steps
  there.
- A report establishes what the host looks like. It never establishes
  credential validity, scopes, billing or quota; that the coordinator enforces
  the declared concurrency and spend limits; that any media matches the
  accepted input locks (#26); that an off-host destination exists, is reachable
  or is independent; tool function beyond a version probe; or factory health.
- `--origin offhost` is an operator attestation. The drill records it, and the
  report marks the off-host requirement `present-unverified` rather than
  proven. `independent_host` compares the source and restore host identities,
  so a drill run on the source host cannot demonstrate independent-host
  recovery.
- The tests use a synthetic tree and the host's own OpenSSL. They prove the
  tools' behaviour, not real-disc extraction, emulator compatibility,
  gameplay parity, deployment or browser support.
