#!/usr/bin/env python3
"""Redacted static host-preparation report for the Neptune research host (#25).

Reads the operator's declaration, `lstat`s declared paths, parses system facts
and runs fixed version probes. It never opens a credential file, reads original
media, calls a provider or GitHub, runs a job or provisions anything, so a report
cannot show that credentials work, spend is enforced or the factory is healthy.
Run it on the host as the coordinator account; see HOST_READINESS.md.
"""
from __future__ import annotations

import argparse
import fnmatch
import grp
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import host_contract as contract

SCHEMA = "neptune.factory-host-readiness.v1"
SCOPE = ("Static host-preparation report from lstat, system-file and version probes. No credential was opened, "
         "no provider or GitHub call was made and no job ran: it does not establish credential validity, "
         "enforced limits, media authenticity or factory health.")
# Fail closed: a probe that could not establish a fact blocks like a wrong fact. "present-unverified"
# means statically sound but not checkable without a live call, so it never blocks.
BLOCKING = ("absent", "misconfigured", "unsupported", "indeterminate")
UNVERIFIED = ("present-unverified",)
PRIVILEGED_GROUPS = ("root", "sudo", "wheel", "docker", "podman", "lxd", "disk", "shadow", "adm")
CONTAINER_SOCKETS = ("/var/run/docker.sock", "/run/docker.sock", "/run/podman/podman.sock")
MINIMUM_PYTHON = (3, 11)
WALK_LIMIT = 100_000
# name, version arguments (None: this interpreter), required, capabilities it serves.
# Baseline tools mirror verify.py; make and c++ are needed by the pinned source builds.
SOFTWARE = (
    ("python3", None, True, ("offline-verification", "tool-preparation")),
    ("git", ("--version",), True, ("offline-verification", "tool-preparation")),
    ("openssl", ("version",), True, ("offline-verification", "backup")),
    ("cc", ("--version",), True, ("offline-verification", "tool-preparation")),
    ("make", ("--version",), True, ("tool-preparation",)),
    ("c++", ("--version",), True, ("tool-preparation",)),
    ("Xvfb", ("-version",), False, ("native-runtime",)),
    ("docker", ("--version",), False, ("container-isolation",)),
    ("ffmpeg", ("-version",), False, ("media-processing",)),
)
TRANSPORTS = (("rclone", ("version",)), ("rsync", ("--version",)), ("ssh", ("-V",)))
NEVER_VERIFIED = (
    "credential validity, scopes, billing and quota",
    "enforcement of the declared concurrency and spend limits by the coordinator",
    "original media authenticity against the accepted input locks (#26)",
    "off-host destination identity, reachability and independence",
    "tool function beyond a version probe",
)


class Probe:
    """Every host access, behind one seam so tests can simulate accounts, mounts and services."""

    def lstat(self, path):
        try:
            return os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return None

    def listdir(self, path):
        return sorted(os.listdir(path))

    def realpath(self, path):
        return os.path.realpath(path)

    def read_text(self, path, limit=1 << 20):
        try:
            with open(path, "rb") as stream:
                return stream.read(limit).decode("utf-8", "replace")
        except (FileNotFoundError, NotADirectoryError):
            return None

    def read_head(self, path, size):
        try:
            with open(path, "rb") as stream:
                return stream.read(size)
        except (FileNotFoundError, NotADirectoryError):
            return None

    def disk_usage(self, path):
        usage = shutil.disk_usage(path)
        return usage.total, usage.free

    def account(self, name):
        try:
            entry = pwd.getpwnam(name)
        except KeyError:
            return None
        gids = set(os.getgrouplist(name, entry.pw_gid))
        groups = set()
        for gid in gids:
            try:
                groups.add(grp.getgrgid(gid).gr_name)
            except KeyError:
                pass
        return {"uid": entry.pw_uid, "gid": entry.pw_gid, "home": entry.pw_dir, "gids": gids, "groups": groups}

    def which(self, name):
        return shutil.which(name, path=contract.TRUSTED_PATH)

    def run(self, argv, timeout=8):
        env = {"PATH": contract.TRUSTED_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        try:
            done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, env=env)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.returncode, done.stdout[:65536].decode("utf-8", "replace"), done.stderr[:65536].decode("utf-8", "replace")

    def system(self):
        return {"system": platform.system(), "machine": platform.machine(), "kernel": platform.release()}

    def cpus(self):
        logical = os.cpu_count() or 0
        usable = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else logical
        return logical, usable

    def python(self):
        return tuple(sys.version_info[:3])

    def now(self):
        return time.time()


def check(identifier, category, status, detail, facts=None, needed_for=(), optional=False):
    return {"id": identifier, "category": category, "status": status, "detail": detail,
            "facts": facts or {}, "needed_for": sorted(needed_for), "optional": optional}


def guarded(identifier, category, needed_for, function):
    """One failing probe becomes an indeterminate (blocking) check; it never aborts or reads as success."""
    try:
        return function()
    except (OSError, ValueError, UnicodeError) as error:
        return [check(identifier, category, "indeterminate", "probe failed: " + type(error).__name__, needed_for=needed_for)]


def mode_bits(st, account):
    """POSIX owner/group/other selection for one account; ACLs and capabilities are not visible."""
    if account["uid"] == 0:
        return True, True, True
    if st.st_uid == account["uid"]:
        bits = (st.st_mode >> 6) & 7
    elif st.st_gid in account["gids"]:
        bits = (st.st_mode >> 3) & 7
    else:
        bits = st.st_mode & 7
    return bool(bits & 4), bool(bits & 2), bool(bits & 1)


def reach(ctx, path, account):
    """Effective (read, write) at a path under the root; every directory from the root needs search permission."""
    relative = posixpath.relpath(path, ctx.root)
    parts = [] if relative == "." else relative.split("/")
    walk = [ctx.root] + [ctx.root + "/" + "/".join(parts[:index]) for index in range(1, len(parts))]
    for directory in walk:
        st = ctx.probe.lstat(directory)
        if st is None or not stat.S_ISDIR(st.st_mode) or not mode_bits(st, account)[2]:
            return False, False
    st = ctx.probe.lstat(path)
    if st is None:
        return False, False
    read, write, search = mode_bits(st, account)
    if stat.S_ISDIR(st.st_mode):
        return read and search, write and search
    return read, write


def access_label(read, write):
    return "read-write" if read and write else "write" if write else "read" if read else "none"


def owner_label(ctx, st):
    for role in contract.ROLES:
        account = ctx.roles[role]
        if account is not None and st.st_uid == account["uid"]:
            return role
    return "root" if st.st_uid == 0 else "other"


def mode_text(st):
    return "%04o" % (st.st_mode & 0o7777)


def unescape(text):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), text)


def parse_mountinfo(text):
    mounts = []
    for line in (text or "").splitlines():
        left, separator, right = line.partition(" - ")
        fields, tail = left.split(" "), right.split(" ")
        if not separator or len(fields) < 6 or len(tail) < 3:
            continue
        mounts.append({"point": unescape(fields[4]), "options": set(fields[5].split(",")),
                       "super_options": set(tail[2].split(",")), "fstype": tail[0]})
    return mounts


def covering_mount(mounts, path):
    best = None
    for mount in mounts:
        point = mount["point"]
        if point == "/" or path == point or path.startswith(point.rstrip("/") + "/"):
            if best is None or len(point) >= len(best["point"]):
                best = mount
    return best


def parse_os_release(text):
    values = {}
    for line in (text or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and re.fullmatch(r"[A-Z_]+", key):
            values[key] = value.strip().strip('"')[:80]
    return {"id": values.get("ID"), "version_id": values.get("VERSION_ID"), "pretty_name": values.get("PRETTY_NAME")}


def parse_meminfo(text):
    wanted = {"MemTotal": "total_bytes", "MemAvailable": "available_bytes", "SwapTotal": "swap_total_bytes"}
    result = {name: None for name in wanted.values()}
    for line in (text or "").splitlines():
        match = re.fullmatch(r"(\w+):\s+(\d+) kB", line.strip())
        if match and match.group(1) in wanted:
            result[wanted[match.group(1)]] = int(match.group(2)) * 1024
    return result


def first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:120]
    return None


def inventory(ctx, path, recursive):
    """Bounded lstat inventory. Names, contents and hashes are never read or reported.

    Non-recursive mode counts only the direct entries of `path`.
    """
    entries = files = size = writable = symlinks = 0
    top = ctx.probe.lstat(path)
    if top is not None and top.st_mode & 0o222:
        writable += 1
    stack, truncated = [path], False
    while stack and not truncated:
        directory = stack.pop()
        for name in ctx.probe.listdir(directory):
            entries += 1
            if entries > WALK_LIMIT:
                truncated = True
                break
            st = ctx.probe.lstat(directory + "/" + name)
            if st is None:
                continue
            if st.st_mode & 0o222:
                writable += 1
            if stat.S_ISLNK(st.st_mode):
                symlinks += 1
            elif stat.S_ISDIR(st.st_mode) and recursive:
                stack.append(directory + "/" + name)
            elif stat.S_ISREG(st.st_mode):
                files += 1
                size += st.st_size
        if not recursive:
            break
    return {"entries": entries, "files": files, "bytes": size, "writable_entries": writable,
            "symlinks": symlinks, "truncated": truncated}


# ---------------------------------------------------------------- host facts

def host_facts(ctx, paths):
    probe, system = ctx.probe, ctx.probe.system()
    logical, usable = probe.cpus()
    filesystems = {}
    for key, path in sorted(paths.items()):
        st = probe.lstat(path)
        if st is None or stat.S_ISLNK(st.st_mode):
            continue
        total, free = probe.disk_usage(path)
        device = "%d:%d" % (os.major(st.st_dev), os.minor(st.st_dev))
        mount = covering_mount(ctx.mounts or [], probe.realpath(path))
        entry = filesystems.setdefault(device, {"keys": [], "total_bytes": total, "free_bytes": free,
                                                "fstype": mount["fstype"] if mount else None})
        entry["keys"].append(key)
    return {"host_id": contract.host_id_from(probe.read_text("/etc/machine-id", 256)),
            "os": parse_os_release(probe.read_text("/etc/os-release", 8192)),
            "architecture": system["machine"], "kernel": system["kernel"],
            "cpus": {"logical": logical, "usable": usable},
            "memory": parse_meminfo(probe.read_text("/proc/meminfo", 65536)),
            "filesystems": [dict(entry, device=device) for device, entry in sorted(filesystems.items())]}


def service_facts(ctx, patterns):
    """Running services, redacted: only operator-watched names; others are counted and digested."""
    probe = ctx.probe
    systemctl = probe.which("systemctl")
    result = probe.run([systemctl, "list-units", "--type=service", "--state=running", "--no-legend", "--plain",
                        "--no-pager"]) if systemctl else None
    if result is None or result[0] != 0:
        return {"status": "unavailable", "running_count": None, "watched": {}, "other_running_count": None, "digest": None}
    names = sorted({line.split()[0] for line in result[1].splitlines()
                    if line.split() and re.fullmatch(r"[A-Za-z0-9_.@:\\-]+\.service", line.split()[0])})
    watched = {pattern: [n for n in names if fnmatch.fnmatchcase(n, pattern)] for pattern in patterns}
    matched = {n for found in watched.values() for n in found}
    return {"status": "ok", "running_count": len(names), "watched": watched,
            "other_running_count": len(names) - len(matched),
            "digest": hashlib.sha256("\n".join(names).encode()).hexdigest()}


# -------------------------------------------------------------------- checks

def platform_check(ctx):
    system = ctx.probe.system()
    supported = system["system"] == "Linux" and system["machine"] == "x86_64"
    return [check("host.platform", "host", "ok" if supported else "unsupported",
                  "Linux x86_64 as the pinned recipes require" if supported else "pinned recipes target Linux x86_64",
                  {"system": system["system"], "architecture": system["machine"]}, ("tool-preparation",))]


def software_checks(ctx):
    probe, results = ctx.probe, []
    for name, arguments, required, needed in SOFTWARE:
        path = probe.which(name)
        identifier = "software." + name
        if arguments is None:
            # The verifier runs under the invoking interpreter, so judge that one, not PATH.
            version = probe.python()
            results.append(check(identifier, "software", "ok" if version >= MINIMUM_PYTHON else "unsupported",
                                 "interpreter running this report",
                                 {"version": "%d.%d.%d" % version, "minimum": "3.11", "system_python3": path is not None},
                                 needed, not required))
            continue
        if path is None:
            results.append(check(identifier, "software", "absent", "not installed", {}, needed, not required))
            continue
        ran = probe.run([path, *arguments])
        version = first_line(ran[1] or ran[2]) if ran else None
        if ran is None or ran[0] != 0 or version is None:
            results.append(check(identifier, "software", "indeterminate", "installed but the version probe failed",
                                 {"path": path}, needed, not required))
        else:
            results.append(check(identifier, "software", "ok", "installed", {"path": path, "version": version},
                                 needed, not required))
    found = []
    for name, arguments in TRANSPORTS:
        if probe.which(name):
            found.append(name)
    results.append(check("software.backup-transport", "software", "ok" if found else "absent",
                         "an off-host transfer tool is installed" if found else "no rclone, rsync or ssh installed",
                         {"available": found}, ("backup",)))
    return results


def identity_checks(ctx):
    results = []
    for role in contract.ROLES:
        name, account = ctx.declaration["roles"][role], ctx.roles[role]
        identifier = "identity." + role
        if name is None:
            results.append(check(identifier, "identity", "absent", "role account not declared", needed_for=("host-isolation",)))
        elif account is None:
            results.append(check(identifier, "identity", "absent", "declared role account does not exist", needed_for=("host-isolation",)))
        elif account["uid"] == 0:
            results.append(check(identifier, "identity", "misconfigured", "role account is root", {"uid": 0}, ("host-isolation",)))
        else:
            results.append(check(identifier, "identity", "ok", "non-root account",
                                 {"uid": account["uid"], "gid": account["gid"]}, ("host-isolation",)))
    coordinator, worker = ctx.roles["coordinator"], ctx.roles["worker"]
    if coordinator is None or worker is None:
        results.append(check("identity.separation", "identity", "indeterminate", "both role accounts are needed to compare",
                             needed_for=("host-isolation",)))
    else:
        separate = coordinator["uid"] != worker["uid"]
        results.append(check("identity.separation", "identity", "ok" if separate else "misconfigured",
                             "coordinator and worker are different accounts" if separate else "coordinator and worker share a uid",
                             needed_for=("host-isolation",)))
    if worker is None:
        return results
    privileged = sorted(set(PRIVILEGED_GROUPS) & worker["groups"])
    results.append(check("identity.worker-privileges", "identity", "misconfigured" if privileged else "ok",
                         "worker belongs to privileged groups" if privileged else "worker has no privileged group",
                         {"privileged_groups": privileged}, ("host-isolation",)))
    exposed, seen = [], set()
    for socket in CONTAINER_SOCKETS:
        st = ctx.probe.lstat(socket)
        if st is None or (st.st_dev, st.st_ino) in seen:
            continue
        seen.add((st.st_dev, st.st_ino))
        read, write, _ = mode_bits(st, worker)
        if read or write:
            exposed.append(posixpath.basename(socket))
    results.append(check("identity.container-sockets", "identity", "misconfigured" if exposed else "ok",
                         "worker can reach a container control socket" if exposed else "no container control socket reachable by the worker",
                         {"reachable": exposed}, ("host-isolation",)))
    return results


def layout_checks(ctx):
    results = []
    expectations = {"repos": "coordinator", "state": "coordinator", "workspaces": None}
    for key, relative in sorted(ctx.declaration["directories"].items()):
        path, identifier = ctx.root + "/" + relative, "layout." + key
        st = ctx.probe.lstat(path)
        if st is None:
            results.append(check(identifier, "layout", "absent", "directory not provisioned", needed_for=("host-isolation",)))
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            results.append(check(identifier, "layout", "misconfigured", "not a real directory (symlink or file)", needed_for=("host-isolation",)))
            continue
        owner, problems, worker = owner_label(ctx, st), [], ctx.roles["worker"]
        known = [role for role in contract.ROLES if ctx.roles[role] is not None]
        if st.st_mode & 0o007:
            problems.append("world-accessible")
        if key == "workspaces" and (owner == "root" or (owner == "other" and known)):
            problems.append("workspaces must be owned by a non-root role account")
        if expectations[key] and ctx.roles[expectations[key]] is not None and owner != expectations[key]:
            problems.append("%s must be owned by the %s account" % (key, expectations[key]))
        access = "unknown"
        if worker is not None:
            read, write = reach(ctx, path, worker)
            access = access_label(read, write)
            if key == "state" and (read or write):
                problems.append("worker can reach durable state")
            if key == "repos" and write:
                problems.append("worker can modify the canonical checkouts")
        results.append(check(identifier, "layout", "misconfigured" if problems else "ok",
                             "; ".join(problems) if problems else "present; no world access",
                             {"owner": owner, "mode": mode_text(st), "worker_access": access}, ("host-isolation",)))
    return results


def input_checks(ctx):
    results = []
    for name, item in sorted(ctx.declaration["inputs"].items()):
        path, tags = ctx.root + "/" + item["path"], item["needed_for"]
        present, protection = "input.%s.present" % name, "input.%s.protection" % name
        st = ctx.probe.lstat(path)
        if st is None:
            results.append(check(present, "input", "absent", "directory not provisioned", needed_for=tags))
            results.append(check(protection, "input", "not-applicable", "directory not provisioned", needed_for=tags))
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            results.append(check(present, "input", "misconfigured", "not a real directory (symlink or file)", needed_for=tags))
            results.append(check(protection, "input", "misconfigured", "use a real directory or bind mount", needed_for=tags))
            continue
        media = item["kind"] == "media"
        found = inventory(ctx, path, recursive=media)
        # Media counts regular files at any depth; private state counts direct entries.
        held = found["files"] if media else found["entries"]
        facts = {"kind": item["kind"], "files": held, "bytes": found["bytes"], "truncated": found["truncated"]}
        results.append(check(present, "input", "ok" if held else "absent",
                             "content present (identity not verified; see #26)" if held else "directory exists but is empty",
                             facts, tags))
        problems, owner = [], owner_label(ctx, st)
        if owner not in ("coordinator", "root") and ctx.roles["coordinator"] is not None:
            problems.append("owned by neither the coordinator nor root")
        if st.st_mode & 0o007:
            problems.append("world-accessible")
        access = "unknown"
        if ctx.roles["worker"] is not None:
            read, write = reach(ctx, path, ctx.roles["worker"])
            access = access_label(read, write)
            if read or write:
                problems.append("worker account can reach private inputs")
        mount = covering_mount(ctx.mounts, ctx.probe.realpath(path)) if ctx.mounts is not None else None
        read_only = bool(mount and ("ro" in mount["options"] or "ro" in mount["super_options"]))
        dedicated = bool(mount and mount["point"] != "/")
        unreadable = False
        if media:
            if found["symlinks"]:
                problems.append("contains symlinks that could leave the read-only input")
            if item["enforcement"] == "mount":
                if ctx.mounts is None:
                    unreadable = True
                elif not (read_only and dedicated):
                    problems.append("no dedicated read-only mount covers this input")
            elif found["writable_entries"]:
                problems.append("entries carry write permission bits")
        facts = {"owner": owner, "mode": mode_text(st), "worker_access": access, "enforcement": item["enforcement"],
                 "read_only_mount": read_only and dedicated if ctx.mounts is not None else None,
                 "mount_fstype": mount["fstype"] if mount else None, "writable_entries": found["writable_entries"],
                 "symlinks": found["symlinks"]}
        if problems:
            results.append(check(protection, "input", "misconfigured", "; ".join(problems), facts, tags))
        elif unreadable:
            results.append(check(protection, "input", "indeterminate", "mount table unreadable; read-only mount unproven", facts, tags))
        else:
            results.append(check(protection, "input", "ok", "owner-only access" + ("; read-only enforced" if media else ""), facts, tags))
    return results


def credential_checks(ctx):
    """Stat-only. Contents are never opened, so no value, size class or hash can reach a report."""
    results, identities = [], {}
    root = ctx.root
    for name, item in sorted(ctx.declaration["credentials"].items()):
        path, role, tags, identifier = item["path"], item["role"], item["needed_for"], "credential." + name
        st = ctx.probe.lstat(path)
        if st is None:
            results.append(check(identifier, "credential", "absent", "credential file not present", {"role": role}, tags))
            continue
        problems, account = [], ctx.roles[role]
        if stat.S_ISLNK(st.st_mode):
            problems.append("is a symlink")
        elif not stat.S_ISREG(st.st_mode):
            problems.append("is not a regular file")
        else:
            identities.setdefault(role, set()).add((st.st_dev, st.st_ino))
            if st.st_size == 0:
                problems.append("is empty")
            if st.st_mode & 0o077:
                problems.append("is accessible to group or other")
        if account is not None and st.st_uid != account["uid"]:
            problems.append("is not owned by the %s account" % role)
        trees = [ctx.repo_root, root + "/" + ctx.declaration["directories"]["repos"],
                 root + "/" + ctx.declaration["directories"]["workspaces"]]
        worker = ctx.roles["worker"]
        if worker is not None and role == "coordinator":
            trees.append(worker["home"])
        if any(contract.inside(path, tree) for tree in trees):
            problems.append("lives in a repository, workspace or worker home")
        parent = ctx.probe.lstat(posixpath.dirname(path))
        if parent is not None:
            if parent.st_mode & 0o022 and not parent.st_mode & stat.S_ISVTX:
                problems.append("parent directory is writable by group or other")
            if account is not None and parent.st_uid not in (0, account["uid"]):
                problems.append("parent directory has an unexpected owner")
        facts = {"role": role, "kind": item["kind"], "mode": mode_text(st), "owner": owner_label(ctx, st)}
        if problems:
            results.append(check(identifier, "credential", "misconfigured", "; ".join(problems), facts, tags))
        else:
            detail = "present with owner-only access; validity, scopes and quota are not checked"
            if account is None:
                detail += "; role account missing so ownership is unchecked"
            results.append(check(identifier, "credential", "present-unverified", detail, facts, tags))
    shared = bool(identities.get("coordinator", set()) & identities.get("worker", set()))
    missing = [role for role in contract.ROLES if not identities.get(role)]
    if shared:
        status, detail = "misconfigured", "one credential file is declared for both roles"
    elif missing:
        status, detail = "absent", "no usable credential file for: " + ", ".join(missing)
    else:
        status = "present-unverified"
        detail = "distinct files per role; identical secret values cannot be detected without reading them"
    results.append(check("credential.separation", "credential", status, detail, needed_for=("host-isolation",)))
    return results


def policy_checks(ctx):
    policy, spend = ctx.declaration["policy"], ctx.declaration["policy"]["spend"]
    missing = [name for name in ("max_concurrent_jobs", "max_concurrent_heavy_jobs") if policy[name] is None]
    results = [check("policy.concurrency", "policy", "absent" if missing else "present-unverified",
                     "not configured: " + ", ".join(missing) if missing else "declared; enforcement by the coordinator is not observed",
                     {"max_concurrent_jobs": policy["max_concurrent_jobs"],
                      "max_concurrent_heavy_jobs": policy["max_concurrent_heavy_jobs"]}, ("provider-jobs",))]
    missing = [name for name, value in spend.items() if value is None]
    results.append(check("policy.spend", "policy", "absent" if missing else "present-unverified",
                         "not configured: " + ", ".join(missing) if missing else "declared; enforcement by the coordinator is not observed",
                         dict(spend), ("provider-jobs",)))
    return results


def backup_checks(ctx):
    backup, now, tags = ctx.declaration["backup"], ctx.probe.now(), ("backup",)
    missing = [name for name in ("key", "max_age_seconds") if backup[name] is None]
    if not backup["sources"]:
        missing.append("sources")
    results = [check("backup.configuration", "backup", "absent" if missing else "ok",
                     "not configured: " + ", ".join(missing) if missing else "sources, key and maximum age declared",
                     {"sources": len(backup["sources"])}, tags)]
    directory = ctx.root + "/" + backup["archive_dir"]
    sidecars = []
    try:
        names = [n for n in ctx.probe.listdir(directory) if re.fullmatch(r"nbk-\d{8}T\d{6}Z-[0-9a-f]{8}\.json", n)]
    except FileNotFoundError:
        names = []
    for name in names[-1000:]:
        try:
            value, digest = contract.read_json(directory + "/" + name, contract.MAX_RECEIPT_BYTES, "Backup sidecar")
            sidecars.append((contract.validate_sidecar(value)["created_epoch"], name, value, digest))
        except contract.DeclarationError:
            continue
    limit = backup["max_age_seconds"]
    if not sidecars:
        results.append(check("backup.archive", "backup", "absent", "no valid archive record in the archive directory", needed_for=tags))
    else:
        created, name, newest, _ = max(sidecars, key=lambda item: item[0])
        archive = directory + "/" + newest["archive"]
        st = ctx.probe.lstat(archive)
        head = ctx.probe.read_head(archive, 13) if st is not None and stat.S_ISREG(st.st_mode) else None
        age = now - created
        facts = {"created_at": newest["created_at"], "age_seconds": round(age), "files": newest["file_count"],
                 "bytes": newest["archive_bytes"], "sqlite_snapshots": newest["sqlite_snapshots"]}
        problems = []
        if st is None or not stat.S_ISREG(st.st_mode):
            problems.append("archive file missing")
        elif st.st_size != newest["archive_bytes"]:
            problems.append("archive size differs from its record")
        elif head != b"NEPTUNE-NBK1\n":
            problems.append("archive does not start with the encrypted-archive header")
        if age < -300:
            problems.append("record is dated in the future")
        elif limit is not None and age > limit:
            problems.append("newest archive is older than the declared maximum age")
        if problems:
            results.append(check("backup.archive", "backup", "misconfigured", "; ".join(problems), facts, tags))
        elif limit is None:
            results.append(check("backup.archive", "backup", "indeterminate",
                                 "archive present with encrypted header; freshness not judged without a maximum age", facts, tags))
        else:
            results.append(check("backup.archive", "backup", "ok", "newest archive present, encrypted header and fresh",
                                 facts, tags))
    results.extend(drill_checks(ctx, sidecars, now, tags))
    return results


def drill_checks(ctx, sidecars, now, tags):
    backup = ctx.declaration["backup"]
    try:
        value, _ = contract.read_json(ctx.root + "/" + backup["drill_receipt"], contract.MAX_RECEIPT_BYTES, "Restore drill receipt")
        drill = contract.validate_drill(value)
    except contract.DeclarationError as error:
        absent = isinstance(error, contract.MissingFile)
        return [check("backup.restore-drill", "backup", "absent" if absent else "misconfigured",
                      "no restore drill receipt" if absent else "receipt rejected: " + str(error), needed_for=tags),
                check("backup.offhost", "backup", "absent", "no restore drill from an off-host copy", needed_for=tags)]
    match = [item for item in sidecars if item[2]["archive_sha256"] == drill["archive_sha256"]]
    age, limit, problems = now - drill["restored_epoch"], backup["max_age_seconds"], []
    if not match:
        problems.append("drill matches no archive record in the archive directory")
    else:
        record = match[0][2]
        if (drill["file_count"], drill["manifest_sha256"]) != (record["file_count"], record["manifest_sha256"]):
            problems.append("drill disagrees with the archive record")
    if drill["files_verified"] != drill["file_count"] or drill["sqlite_ok"] != drill["sqlite_checked"]:
        problems.append("drill did not verify every file and database")
    if age < -300:
        problems.append("receipt is dated in the future")
    elif limit is not None and age > limit:
        problems.append("drill is older than the declared maximum age")
    facts = {"restored_at": drill["restored_at"], "age_seconds": round(age), "files_verified": drill["files_verified"],
             "bytes_verified": drill["bytes_verified"], "sqlite_ok": drill["sqlite_ok"],
             "independent_host": drill["independent_host"]}
    if problems:
        results = [check("backup.restore-drill", "backup", "misconfigured", "; ".join(problems), facts, tags)]
    elif limit is None:
        results = [check("backup.restore-drill", "backup", "indeterminate",
                         "verified after decryption; freshness not judged without a maximum age", facts, tags)]
    else:
        results = [check("backup.restore-drill", "backup", "ok",
                         "every file and database verified after decryption", facts, tags)]
    if drill["origin"] != "offhost":
        results.append(check("backup.offhost", "backup", "misconfigured",
                             "drill restored a local copy; fetch the archive from the off-host destination", facts, tags))
    else:
        detail = "off-host origin is operator-attested, not observed"
        if drill["independent_host"] is not True:
            detail += "; restored on the source host, so independent-host recovery is unproven"
        results.append(check("backup.offhost", "backup", "present-unverified", detail, facts, tags))
    return results


# ------------------------------------------------------------------- report

def root_check(ctx):
    st = ctx.probe.lstat(ctx.root)
    if st is None:
        return check("layout.root", "layout", "absent", "root directory not provisioned", needed_for=("host-isolation",))
    if not stat.S_ISDIR(st.st_mode) or ctx.probe.realpath(ctx.root) != ctx.root:
        return check("layout.root", "layout", "misconfigured", "root is not a real path; declare its resolved location",
                     needed_for=("host-isolation",))
    return check("layout.root", "layout", "ok", "present", {"owner": owner_label(ctx, st), "mode": mode_text(st)},
                 ("host-isolation",))


def summarize(checks):
    counts, capabilities = {}, {}
    for item in checks:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        for tag in item["needed_for"]:
            entry = capabilities.setdefault(tag, {"blockers": [], "unverified": []})
            if item["status"] in BLOCKING and not item["optional"]:
                entry["blockers"].append(item["id"])
            elif item["status"] in UNVERIFIED:
                entry["unverified"].append(item["id"])
    for entry in capabilities.values():
        entry["state"] = "blocked" if entry["blockers"] else "static-checks-pass"
    blocking = sorted(c["id"] for c in checks if c["status"] in BLOCKING and not c["optional"])
    absent = {}
    for item in checks:
        if item["status"] == "absent":
            absent.setdefault(item["category"], []).append(item["id"])
    installed = {c["id"][len("software."):] for c in checks
                 if c["category"] == "software" and c["status"] == "ok" and c["id"] != "software.backup-transport"}
    for item in checks:
        if item["id"] == "software.backup-transport":
            installed.update(item["facts"].get("available", []))
    return {"static_checks": "fail" if blocking else "pass", "counts": dict(sorted(counts.items())),
            "blocking": blocking, "absent_by_category": {k: sorted(v) for k, v in sorted(absent.items())},
            "installed_software": sorted(installed),
            "capabilities": dict(sorted(capabilities.items())),
            "unverified": sorted(c["id"] for c in checks if c["status"] in UNVERIFIED),
            "never_verified_by_this_report": list(NEVER_VERIFIED), "factory_health": "not-assessed"}


def build_report(declaration, declaration_sha256, probe=None, repo_root=None):
    probe = probe or Probe()
    repo_root = repo_root or str(Path(__file__).resolve().parents[2])
    root = declaration["root"]
    text = probe.read_text("/proc/self/mountinfo")
    ctx = SimpleNamespace(probe=probe, declaration=declaration, root=root, repo_root=repo_root,
                          mounts=parse_mountinfo(text) if text is not None else None, roles={})
    for role in contract.ROLES:
        name = declaration["roles"][role]
        ctx.roles[role] = probe.account(name) if name else None
    paths = {"root": root}
    paths.update({"directory:" + k: root + "/" + v for k, v in declaration["directories"].items()})
    paths.update({"input:" + k: root + "/" + v["path"] for k, v in declaration["inputs"].items()})
    groups = [("host", ("tool-preparation",), platform_check), ("software", ("tool-preparation",), software_checks),
              ("identity", ("host-isolation",), identity_checks), ("layout", ("host-isolation",), layout_checks),
              ("input", (), input_checks), ("credential", (), credential_checks), ("policy", ("provider-jobs",), policy_checks),
              ("backup", ("backup",), backup_checks)]
    checks = guarded("layout.root", "layout", ("host-isolation",), lambda: [root_check(ctx)])
    for category, tags, function in groups:
        checks.extend(guarded(category + ".probe", category, tags, lambda f=function: f(ctx)))
    head = None
    git = probe.which("git")
    ran = probe.run([git, "-C", repo_root, "rev-parse", "HEAD"]) if git else None
    if ran and ran[0] == 0 and contract.HEX[40].fullmatch(ran[1].strip()):
        head = ran[1].strip()
    try:
        facts = host_facts(ctx, paths)
        services = service_facts(ctx, declaration["services"]["watch"])
    except (OSError, ValueError, UnicodeError) as error:
        facts, services = {"error": "host facts unavailable: " + type(error).__name__}, {"status": "unavailable"}
    return {"schema": SCHEMA, "scope": SCOPE,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(probe.now())),
            "identity": {"tool_sha256": contract.tool_sha256(), "declaration_sha256": declaration_sha256,
                         "repository_head": head},
            "host": dict(facts, services=services), "checks": checks, "summary": summarize(checks)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("template", help="print a declaration with unconfigured limits and accounts")
    report = sub.add_parser("report", help="inspect this host against a declaration")
    report.add_argument("--declaration", type=Path, required=True)
    report.add_argument("--output", type=Path, help="write the report to a new file instead of stdout")
    report.add_argument("--strict", action="store_true", help="exit 1 unless every static check passes")
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            print(json.dumps(contract.template(), indent=2, sort_keys=True))
            return 0
        declaration, digest = contract.load_declaration(args.declaration)
        result = build_report(declaration, digest)
        if args.output:
            contract.write_json(args.output, result)
            print(json.dumps({"report": str(args.output), "static_checks": result["summary"]["static_checks"],
                              "blocking": len(result["summary"]["blocking"])}))
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if args.strict and result["summary"]["static_checks"] != "pass" else 0
    except (ValueError, OSError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
