"""Operator host declaration and receipt contracts for the #25 host tools.

The declaration is written on the research host by the operator. It names
accounts, paths and explicit limits; it never carries secret values, commands or
free text, so nothing in it can be echoed into a report as a secret. Unknown
fields, duplicate keys, odd paths and out-of-range limits fail instead of being
defaulted. A null limit means "not configured yet" and is reported as absent:
this module invents no concurrency, spend, retention or schedule value.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

SCHEMA = "neptune.factory-host-declaration.v1"
SIDECAR_SCHEMA = "neptune.backup-archive.v1"
DRILL_SCHEMA = "neptune.backup-restore-drill.v1"
MAX_DECLARATION_BYTES = 64 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
# Fixed lookup path for every probe and child process; never the caller's PATH,
# which may name user-writable directories.
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ROLES = ("coordinator", "worker")
DIRECTORIES = ("repos", "state", "workspaces")
INPUT_KINDS = ("media", "private")
ENFORCEMENT = ("mount", "permissions")
CREDENTIAL_KINDS = ("github", "provider", "backup", "ssh")
DECLARABLE_CAPABILITIES = ("backup", "power-experiments", "provider-jobs", "repository-intake",
                           "repository-publication", "saturn-experiments")
ARCHIVE_NAME = re.compile(r"nbk-\d{8}T\d{6}Z-[0-9a-f]{8}")

ACCOUNT = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,39}")
COMPONENT = re.compile(r"[A-Za-z0-9._@+=,~-]+(?: [A-Za-z0-9._@+=,~-]+)*")
PATTERN = re.compile(r"[A-Za-z0-9_.@*?-]{1,80}")
HEX = {length: re.compile(r"[0-9a-f]{%d}" % length) for length in (16, 40, 64)}


class DeclarationError(ValueError):
    pass


class MissingFile(DeclarationError):
    """The named file does not exist; callers report it as absent rather than malformed."""


def reject(message):
    raise DeclarationError(message)


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        reject(label + " must have exactly these fields: " + ", ".join(sorted(keys)))
    return value


def components(value, label, absolute):
    if not isinstance(value, str) or not 0 < len(value) <= 240 or value.startswith("/") != absolute:
        reject(label + (" must be a normalised absolute path" if absolute else " must be a normalised relative path"))
    parts = (value[1:] if absolute else value).split("/")
    if not parts or any(not COMPONENT.fullmatch(part) or part in (".", "..") for part in parts):
        reject(label + " contains an empty, dotted or unsupported path component")
    return value


def relative(value, label):
    return components(value, label, False)


def absolute(value, label):
    return components(value, label, True)


def overlaps(left, right):
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def inside(path, parent):
    return path == parent or path.startswith(parent + "/")


def count(value, label, low, high):
    if value is None:
        return None
    if type(value) is not int or not low <= value <= high:
        reject("%s must be null or an integer from %d to %d" % (label, low, high))
    return value


def money(value, label):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1_000_000:
        reject(label + " must be null or a finite non-negative amount")
    return value


def capabilities(value, label):
    if (not isinstance(value, list) or not 1 <= len(value) <= len(DECLARABLE_CAPABILITIES)
            or len(set(value)) != len(value) or any(tag not in DECLARABLE_CAPABILITIES for tag in value)):
        reject(label + " must list unique known capabilities")
    return value


def validate(value):
    """Return the declaration unchanged when it is fully valid, else raise."""
    exact(value, ("schema", "root", "roles", "directories", "inputs", "credentials", "policy", "backup", "services"),
          "declaration")
    if value["schema"] != SCHEMA:
        reject("Unsupported host declaration schema")
    root = absolute(value["root"], "root")
    exact(value["roles"], ROLES, "roles")
    for role, account in value["roles"].items():
        if account is not None and not (isinstance(account, str) and ACCOUNT.fullmatch(account)):
            reject("roles.%s must be null or a Unix account name" % role)
    exact(value["directories"], DIRECTORIES, "directories")
    claimed = {}
    for name, path in value["directories"].items():
        claimed[relative(path, "directories." + name)] = "directory " + name
    inputs = value["inputs"]
    if not isinstance(inputs, dict) or not 1 <= len(inputs) <= 32:
        reject("inputs must name between 1 and 32 private input directories")
    for name, item in inputs.items():
        if not NAME.fullmatch(name):
            reject("Input names are lowercase letters, digits and hyphens")
        exact(item, ("path", "kind", "enforcement", "needed_for"), "input " + name)
        claimed[relative(item["path"], "input %s path" % name)] = "input " + name
        if item["kind"] not in INPUT_KINDS:
            reject("input %s kind must be media or private" % name)
        if item["kind"] == "media" and item["enforcement"] not in ENFORCEMENT:
            reject("media input %s must require mount or permissions enforcement" % name)
        if item["kind"] == "private" and item["enforcement"] is not None:
            reject("private input %s must have null enforcement" % name)
        capabilities(item["needed_for"], "input %s needed_for" % name)
    if len(claimed) != len(value["directories"]) + len(inputs):
        reject("Layout and input paths must be distinct")
    for left in claimed:
        for right in claimed:
            if left < right and overlaps(left, right):
                reject("%s overlaps %s; workers could reach private inputs" % (claimed[left], claimed[right]))
    credentials = value["credentials"]
    if not isinstance(credentials, dict) or len(credentials) > 32:
        reject("credentials must name at most 32 credential files")
    seen = set()
    for name, item in credentials.items():
        if not NAME.fullmatch(name):
            reject("Credential names are lowercase letters, digits and hyphens")
        exact(item, ("role", "path", "kind", "needed_for"), "credential " + name)
        if item["role"] not in ROLES or item["kind"] not in CREDENTIAL_KINDS:
            reject("credential %s needs a known role and kind" % name)
        if absolute(item["path"], "credential %s path" % name) in seen:
            reject("Credential paths must be distinct")
        seen.add(item["path"])
        capabilities(item["needed_for"], "credential %s needed_for" % name)
    policy = value["policy"]
    exact(policy, ("max_concurrent_jobs", "max_concurrent_heavy_jobs", "spend"), "policy")
    jobs = count(policy["max_concurrent_jobs"], "policy.max_concurrent_jobs", 1, 64)
    heavy = count(policy["max_concurrent_heavy_jobs"], "policy.max_concurrent_heavy_jobs", 1, 64)
    if jobs is not None and heavy is not None and heavy > jobs:
        reject("Heavy jobs cannot exceed total concurrent jobs")
    spend = policy["spend"]
    exact(spend, ("currency", "daily_cap", "monthly_cap", "paid_fallback_allowed"), "policy.spend")
    if spend["currency"] is not None and not (isinstance(spend["currency"], str) and re.fullmatch(r"[A-Z]{3}", spend["currency"])):
        reject("policy.spend.currency must be null or a three-letter code")
    daily, monthly = money(spend["daily_cap"], "daily_cap"), money(spend["monthly_cap"], "monthly_cap")
    if daily is not None and monthly is not None and daily > monthly:
        reject("The daily cap cannot exceed the monthly cap")
    if spend["paid_fallback_allowed"] is not None and type(spend["paid_fallback_allowed"]) is not bool:
        reject("policy.spend.paid_fallback_allowed must be null or a boolean")
    backup = value["backup"]
    exact(backup, ("archive_dir", "drill_receipt", "sources", "key", "max_age_seconds"), "backup")
    archive_dir = relative(backup["archive_dir"], "backup.archive_dir")
    relative(backup["drill_receipt"], "backup.drill_receipt")
    sources = backup["sources"]
    if not isinstance(sources, list) or len(sources) > 64 or len(set(sources)) != len(sources):
        reject("backup.sources must be a list of at most 64 distinct paths")
    media = [item["path"] for item in inputs.values() if item["kind"] == "media"]
    refused = [("original media", media), ("repos/workspaces", [value["directories"]["repos"], value["directories"]["workspaces"]])]
    for source in sources:
        relative(source, "backup source")
        # A source may contain the archive directory (it is skipped), never sit in it.
        if inside(source, archive_dir):
            reject("A backup source cannot be the archive directory or inside it")
        for label, paths in refused:
            if any(overlaps(source, path) for path in paths):
                reject("Backups never include %s: keep fingerprints in manifests instead" % label)
        for item in credentials.values():
            if inside(item["path"], root + "/" + source):
                reject("A backup source would archive a credential file")
    if backup["key"] is not None:
        key = credentials.get(backup["key"])
        if not key or key["kind"] != "backup" or key["role"] != "coordinator":
            reject("backup.key must name a coordinator credential of kind backup")
    if backup["max_age_seconds"] is not None:
        count(backup["max_age_seconds"], "backup.max_age_seconds", 3600, 366 * 86400)
    services = value["services"]
    exact(services, ("watch",), "services")
    watch = services["watch"]
    if not isinstance(watch, list) or len(watch) > 32 or len(set(watch)) != len(watch) \
            or any(not (isinstance(p, str) and PATTERN.fullmatch(p)) for p in watch):
        reject("services.watch must list at most 32 distinct unit-name patterns")
    return value


def template():
    """Starting declaration using the docs/restart/REQUIREMENTS.md layout.

    Limits and accounts are null: an unedited template reports them absent
    rather than silently granting any concurrency or spend.
    """
    media = {"enforcement": "mount", "kind": "media"}
    return {
        "schema": SCHEMA,
        "root": "/srv/neptune",
        "roles": {"coordinator": None, "worker": None},
        "directories": {"repos": "repos", "state": "state", "workspaces": "workspaces"},
        "inputs": {
            "saturn-disc": dict(media, path="private/disc", needed_for=["saturn-experiments"]),
            "saturn-bios": dict(media, path="private/bios", needed_for=["saturn-experiments"]),
            "power-reference": dict(media, path="private/power", needed_for=["power-experiments"]),
            "emulator": {"kind": "private", "enforcement": None, "path": "private/emulator", "needed_for": ["saturn-experiments"]},
            "emulator-settings": {"kind": "private", "enforcement": None, "path": "private/settings", "needed_for": ["saturn-experiments"]},
            "manifests": {"kind": "private", "enforcement": None, "path": "private/manifests", "needed_for": ["saturn-experiments"]},
            "captures": {"kind": "private", "enforcement": None, "path": "private/captures", "needed_for": ["saturn-experiments"]},
        },
        "credentials": {
            "github-coordinator": {"role": "coordinator", "kind": "github", "path": "/etc/neptune/coordinator/github-app.pem",
                                   "needed_for": ["repository-intake", "repository-publication"]},
            "github-worker": {"role": "worker", "kind": "github", "path": "/etc/neptune/worker/github-token",
                              "needed_for": ["repository-intake"]},
            "provider-coordinator": {"role": "coordinator", "kind": "provider", "path": "/etc/neptune/coordinator/provider-key",
                                     "needed_for": ["provider-jobs"]},
            "backup-key": {"role": "coordinator", "kind": "backup", "path": "/etc/neptune/coordinator/backup.key",
                           "needed_for": ["backup"]},
        },
        "policy": {"max_concurrent_jobs": None, "max_concurrent_heavy_jobs": None,
                   "spend": {"currency": None, "daily_cap": None, "monthly_cap": None, "paid_fallback_allowed": None}},
        "backup": {"archive_dir": "state/backup/outbox", "drill_receipt": "state/backup/restore-drill.json",
                   "sources": ["state", "private/manifests", "private/captures", "private/settings"],
                   "key": "backup-key", "max_age_seconds": None},
        "services": {"watch": ["neptune-*.service", "repo-factory*.service"]},
    }


def strict_json(raw, label):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                reject("Duplicate JSON key in " + label)
            result[key] = item
        return result

    def constant(_name):
        raise DeclarationError("Non-finite JSON number in " + label)

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    except DeclarationError:
        raise
    except (ValueError, RecursionError) as error:
        raise DeclarationError("%s is not valid JSON (%s)" % (label, type(error).__name__)) from None
    if not isinstance(value, dict):
        reject(label + " must be a JSON object")
    return value


def read_json(path, limit, label):
    """Bounded read of one regular file with no symlink component; returns (value, sha256)."""
    path = Path(os.path.abspath(path))
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        reject(label + " path must not contain symlinks")
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            reject(label + " must be a regular file")
        with open(path, "rb") as stream:
            raw = stream.read(limit + 1)
    except FileNotFoundError:
        raise MissingFile(label + " is missing") from None
    except OSError as error:
        reject("%s cannot be read (%s)" % (label, type(error).__name__))
    if len(raw) > limit:
        reject(label + " exceeds its size bound")
    return strict_json(raw, label), hashlib.sha256(raw).hexdigest()


def load_declaration(path):
    value, digest = read_json(path, MAX_DECLARATION_BYTES, "Host declaration")
    return validate(value), digest


def write_json(path, value, replace=False):
    """Write bounded JSON with no symlink following.

    Exclusive by default so evidence is never overwritten; `replace` stages a
    private temporary file and renames it over a regular file or nothing.
    """
    path = os.path.abspath(path)
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    target = path + ".tmp-" + os.urandom(4).hex() if replace else path
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    except FileExistsError:
        reject("Refusing to overwrite existing evidence: " + os.path.basename(path))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
                reject("Refusing to replace a non-regular receipt")
            os.replace(target, path)
    except BaseException:
        if os.path.lexists(target):
            os.unlink(target)
        raise


def host_id_from(machine_id):
    """Stable, non-reversible host identity: never the hostname, address or raw machine id."""
    text = (machine_id or "").strip().encode()
    return hashlib.sha256(b"neptune-host-id-v1\0" + text).hexdigest() if text else None


def host_id(path="/etc/machine-id"):
    try:
        with open(path, "rb") as stream:
            return host_id_from(stream.read(256).decode("ascii", "replace"))
    except OSError:
        return None


def file_sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tool_sha256():
    """Identity of the tool sources that produced a report or backup receipt."""
    here = Path(__file__).resolve().parent
    names = ("host_backup.py", "host_contract.py", "host_readiness.py")
    return hashlib.sha256(json.dumps({n: file_sha256(here / n) for n in names}, sort_keys=True).encode()).hexdigest()


def shape(value, spec, label):
    """Check a receipt against {field: predicate}; unknown or missing fields fail."""
    if not isinstance(value, dict) or set(value) != set(spec):
        reject(label + " has missing or unknown fields")
    for name, check in spec.items():
        if not check(value[name]):
            reject("%s field %s is invalid" % (label, name))
    return value


def is_int(low=0, high=2**62):
    return lambda v: type(v) is int and low <= v <= high


def is_hex(length, nullable=False):
    return lambda v: (v is None and nullable) or (isinstance(v, str) and HEX[length].fullmatch(v) is not None)


def is_in(*choices):
    return lambda v: isinstance(v, str) and v in choices


def is_bool(nullable=False):
    return lambda v: type(v) is bool or (v is None and nullable)


def is_stamp(v):
    return isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", v) is not None


def is_paths(v):
    try:
        return isinstance(v, list) and len(v) <= 64 and all(relative(item, "path") for item in v)
    except DeclarationError:
        return False


def validate_sidecar(value):
    spec = {"schema": lambda v: v == SIDECAR_SCHEMA, "created_epoch": is_int(), "created_at": is_stamp,
            "format": lambda v: v == "NBK1", "archive": lambda v: isinstance(v, str) and v.endswith(".nbk")
            and ARCHIVE_NAME.fullmatch(v[:-4]) is not None,
            "archive_bytes": is_int(1), "archive_sha256": is_hex(64), "manifest_sha256": is_hex(64),
            "file_count": is_int(), "directory_count": is_int(), "plaintext_bytes": is_int(),
            "sqlite_snapshots": is_int(), "sources": is_paths, "excluded": is_paths,
            "key_fingerprint": is_hex(16), "host_id": is_hex(64, True), "tool_sha256": is_hex(64)}
    return shape(value, spec, "Backup sidecar")


def validate_drill(value):
    spec = {"schema": lambda v: v == DRILL_SCHEMA, "restored_epoch": is_int(), "restored_at": is_stamp,
            "archive_sha256": is_hex(64), "archive_bytes": is_int(1), "sidecar_sha256": is_hex(64),
            "manifest_sha256": is_hex(64), "key_fingerprint": is_hex(16), "file_count": is_int(),
            "files_verified": is_int(), "directory_count": is_int(), "bytes_verified": is_int(),
            "sqlite_checked": is_int(), "sqlite_ok": is_int(), "origin": is_in("offhost", "local"),
            "origin_attested": lambda v: v is True, "source_host_id": is_hex(64, True),
            "restore_host_id": is_hex(64, True), "independent_host": is_bool(True),
            "tool_sha256": is_hex(64), "retained": is_bool()}
    return shape(value, spec, "Restore drill receipt")
