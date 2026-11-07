# Requirements and operator handoff

## Current resolved inputs (30 October 2026)

USA/Japan discs and BIOS are already supplied under `/home/dev/Sega-Saturn-BIOS/`
and accepted through #467/#468/#473. Do not ask for them again. Existing Elgl Repo
Factory/shared supported provider access is authorised through #33; inspect actual
health, quotas and ownership. The checklist below describes capabilities to audit,
not a request to repurchase or reprovision everything. Record only demonstrated
remaining blockers in #48. Read [research execution](RESEARCH_EXECUTION.md).

## Provisioning checklist

| Item | Exact requirement | Purpose |
| --- | --- | --- |
| Research VPS | Reuse the existing x86_64 Linux VPS and one bounded job initially; measure available CPU/RAM/disk before expanding | Separate coordinator needs from emulator/build load. No upgrade or new machine is required by this document. |
| Access | Hostname/IP, SSH username and port, and a secure way to provision an SSH public key; a sudo-capable operator account | Install and diagnose services. Do not paste private keys/passwords into GitHub issues or chat. |
| Reference disc | One complete BIN/CUE set with every referenced track, or a CHD, for a precisely identified release/region | Reproducible reference. Avoid a bare executable or incomplete BIN. Keep an unmodified source copy. |
| BIOS | Matching Saturn BIOS available on the research host | Boot the selected release with the chosen emulator. The operator supplies material they are authorised to use. |
| Power Bomberman reference | Developer-linked client, matching local server and included manual; begin with the documented 0.7.8c release and pin actual hashes | A separate reference for feature and network experiments; the factory can obtain public releases where available. |
| Model access | At least one supported provider credential with working billing/quota, provisioned on the VPS | Run unattended AI jobs. Current chat access is not itself a VPS credential. |
| Spend limit | Choose an explicit daily/monthly AI cap and whether paid fallback is allowed | Prevent uncontrolled continuous usage. Do not start paid workers until configured. |
| Repository access | Game repo read/write; decoded private asset publication authorised through #512; use separate intake/worker/merger roles | Current ChatGPT GitHub access works, but the VPS needs its own credentials. |
| Private backup | Off-host encrypted backup destination and credentials configured locally | Preserve disc fingerprints, traces, job database and research progress. |

The initial lab needs no domain, GPU, paid sprite extractor or public game server.
A GPU might later help vision/local models; benchmark that requirement first.
Subscriptions may be used only through supported provider-native integrations.
Verify unattended access and quotas; do not assume subscription login can be
reused as an OpenHands API credential. A single funded API provider is enough to
prove the first live job. No specific model ID is hard-coded before a live check.

The [host preparation tooling](../../tools/factory/HOST_READINESS.md) (#25) turns
this checklist into a declared, checkable state: the operator writes a
declaration of accounts, paths, credential files, concurrency and spend limits,
the tool reports the host against it, and it keeps encrypted off-host backups
with a verified restore. It purchases nothing, provisions no service and reports
absent media and absent provider credentials apart from installed software.

## GitHub configuration for the VPS

Prefer narrowly scoped GitHub App installation tokens. Start with a single-repo
installation for the game and scoped access to the asset repo for the authorised decoded-content publisher. Required features:

- Read repository contents, issues, PRs and check results.
- Create branches, commits and PRs for implementation.
- Create/update issues for trusted planning and evidence reports.
- Separate merge authority from the worker. Keep the private app key in the
  coordinator's secret store and issue short-lived credentials.
- CI workflow changes need the corresponding workflow permission where applicable.
- Branch rules and required checks are an administrator setup step. Do not enable
  unattended merges until applicable exact-head/current-base checks are enforced.
  No required approving review: follow MERGE_POLICY.md and preserve unrelated protections.

Account-wide administrator tokens and repository secrets are not worker inputs.
Untrusted community issues must not directly launch code with privileged access.

## Software to install/build (factory work, not purchases)

| Component | Plan |
| --- | --- |
| Git, Git LFS, Python | Python 3.11+ for current lab tools; use lockfiles for future dependencies |
| Container runtime | Docker Engine/Compose; isolated workers with constrained resources |
| Godot | Adopt the latest stable release with matching native addons and export templates; refresh exact pins/hashes and validate compatibility under [the dependency policy](DEPENDENCY_POLICY.md) |
| Emulator | Evaluate/pin Beetle Saturn via libretro; build a small noninteractive frontend and instrumented core |
| Graphics debugging | Use Yabause/Kronos source as reference where useful; verify against the chosen reference emulator |
| Reverse engineering | Ghidra, its required JDK, headless scripts and validated Saturn loader support |
| Factory | Pin the coordinator and supported Codex CLI or OpenHands adapter; reuse the durable job store and verify the actual execution identity/limits |
| Image/trace processing | Python imaging tools and FFmpeg as needed; CLI processing with reproducible configuration |
| Monitoring/backups | Structured logs, health checks, bounded storage retention and restoration tests |

The [preparation CLI](../../tools/factory/PROVISIONING.md) now supplies pinned
Godot installation and Beetle Saturn source build/smoke recipes. Other tool
families and automatic lifecycle resumption are tracked in #518 / FACTORY-017.
Routine free tool setup is factory work; do not ask Elgan to install emulators
manually. Keep preparation separate from offline verification, using trusted
sources and the existing restricted environments.

## Storage layout

Suggested locations, created during provisioning:

```text
/srv/neptune/repos/               game and asset checkouts
/srv/neptune/private/disc/        original disc image and tracks
/srv/neptune/private/bios/        BIOS
/srv/neptune/private/emulator/    pinned core executable/build
/srv/neptune/private/power/       pinned Power Bomberman client/server/manual
/srv/neptune/private/settings/    actual emulator configuration
/srv/neptune/private/manifests/   input locks and inventories
/srv/neptune/private/captures/    states, traces and original reference captures
/srv/neptune/state/              durable factory state
/srv/neptune/workspaces/         disposable implementation workspaces
```

Mount original media read-only into capture jobs. Credentials live outside both
repositories and worker mounts. Retain hashes in metadata without placing original
media in git. Capture recordings may contain original assets and belong in private
research storage until distribution permissions are established.

Power Bomberman desktop experiments also need a working display/input/capture
environment. Evaluate the official Linux release with a virtual display first;
record renderer and timing limits. Do not assume a GPU or Windows VM is necessary
until a bounded launch/capture test establishes the host's actual requirements.

## Required later, before public community launch

- Domain and DNS access; TLS certificates and a transactional email service.
- Production game hosting separated from research/build load.
- Object storage/CDN for permitted packs, downloads and previews, with versioning.
- PostgreSQL; Nakama for shared identities/social features; a separate community
  API/metadata store where requirements exceed Nakama's supported storage APIs.
- WebRTC signalling and a TURN service with tested deployment/bandwidth limits.
- A TypeScript website and Godot web export; signed short-lived launch tickets.
- Admin/moderation tools, content reports, upload validation, rate limits,
  privacy controls, account deletion and backup-restoration handling.
- Permission/licensing for material distributed to players. Owning a disc,
  extracting data or keeping a repository private does not itself grant redistribution rights.

## First operator handoff

Supply only the VPS host/user/port, reference release/region, local input paths,
chosen provider and spending cap. Provision secrets directly on the host using a
secure channel. The implementation can proceed on GitHub before this handoff;
live emulation and the continuous paid factory depend on it.
