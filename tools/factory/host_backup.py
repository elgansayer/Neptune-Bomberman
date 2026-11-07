#!/usr/bin/env python3
"""Encrypted research/state backups and restore drills for the Neptune host (#25).

An archive is a tar stream of the declared sources plus a trailing manifest of
SHA-256 hashes, encrypted with AES-256-CTR by the host's OpenSSL and authenticated
with HMAC-SHA256 (encrypt-then-MAC). Both keys derive through HKDF-SHA256 from a
random 256-bit key file and a per-archive salt, so no key reaches argv or the
environment. Restore verifies the tag before decrypting anything, rejects unsafe
members, checks every file against the manifest and records a drill receipt.

Moving the archive off the host and fetching it back is the operator's step; the
receipt records where the restored copy came from as an attestation, not proof.
Original media is never archived. Run as the coordinator account.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from urllib.parse import quote

import host_contract as contract

MANIFEST_SCHEMA = "neptune.backup-manifest.v1"
MAGIC = b"NEPTUNE-NBK1\n"
SALT_BYTES = 32
TAG_BYTES = 32
HEADER_BYTES = len(MAGIC) + SALT_BYTES
OPENSSL_SALTED = 16   # "Salted__" plus the 8-byte salt that `openssl enc` writes first
CIPHER = ("enc", "-aes-256-ctr", "-pbkdf2", "-md", "sha256", "-iter", "10000", "-salt")
CHUNK = 1 << 20
MAX_FILES = 200_000
MAX_NAME = 1024
MAX_MANIFEST_BYTES = 128 * 1024 * 1024
SQLITE_SUFFIXES = (".sqlite", ".sqlite3", ".db")
SQLITE_COMPANIONS = ("-wal", "-shm", "-journal")
SQLITE_MAGIC = b"SQLite format 3\x00"
SPARE_BYTES = 64 * 1024 * 1024


class BackupError(ValueError):
    pass


def fail(message):
    raise BackupError(message)


# ------------------------------------------------------------------- crypto

def hkdf(key, salt, info, length=32):
    """RFC 5869 HKDF-SHA256 (checked against the RFC test vector in the tests)."""
    prk = hmac.new(salt, key, hashlib.sha256).digest()
    output, block, counter = b"", b"", 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def derive(key, salt):
    """Independent cipher passphrase and MAC key for one archive."""
    return hkdf(key, salt, b"neptune-nbk1 openssl passphrase").hex().encode(), hkdf(key, salt, b"neptune-nbk1 mac")


def fingerprint(key):
    return hmac.new(key, b"neptune-nbk1 key fingerprint", hashlib.sha256).hexdigest()[:16]


def private_directory(path):
    st = os.lstat(path)
    return stat.S_ISDIR(st.st_mode) and st.st_uid in (0, os.geteuid()) and not st.st_mode & 0o022


def ensure_directory(path):
    """Create the missing levels of a directory chain with owner-only permissions.

    A symlinked level is refused: the operator declares real paths, and a link could
    move an archive or a key outside the declared layout.
    """
    path = os.path.abspath(path)
    for level in (path, *Path(path).parents):
        if os.path.islink(level):
            fail("refusing to use a symlinked directory: " + str(level))
    missing, current = [], path
    while not os.path.isdir(current):
        if os.path.exists(current):
            fail("refusing to use a path that is not a directory: " + current)
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for level in reversed(missing):
        try:
            os.mkdir(level, 0o700)
        except FileExistsError:
            pass
    if not private_directory(path):
        fail("the directory must not be writable by group or other: " + path)
    return path


def read_key(path):
    """Load the key after refusing an unsafe file. The value never leaves this process."""
    path = os.path.abspath(path)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        fail("backup key file is missing; create it with keygen")
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
        fail("backup key must be a regular file owned by this account with mode 0600")
    if not private_directory(os.path.dirname(path)):
        fail("backup key directory must not be writable by group or other")
    with open(path, "rb") as stream:
        raw = stream.read(129)
    text = raw.decode("ascii", "replace").strip()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        fail("backup key file must hold 64 lowercase hex characters")
    return bytes.fromhex(text)


def make_key(path):
    path = os.path.abspath(path)
    ensure_directory(os.path.dirname(path))
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        fail("a backup key already exists; existing keys are never replaced")
    key = os.urandom(32)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(key.hex().encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return fingerprint(key)


def openssl_binary():
    import shutil as _shutil
    binary = _shutil.which("openssl", path=contract.TRUSTED_PATH)
    if binary is None:
        fail("OpenSSL is not installed; install it before taking backups")
    return binary


class Cipher:
    """One `openssl enc` child. The passphrase travels over an inherited pipe, never argv or environment."""

    def __init__(self, passphrase, decrypt, stdin, stdout):
        read_end, write_end = os.pipe()
        try:
            os.write(write_end, passphrase + b"\n")
        finally:
            os.close(write_end)
        self.errors = tempfile.TemporaryFile()
        argv = [openssl_binary(), *CIPHER, "-pass", "fd:%d" % read_end] + (["-d"] if decrypt else [])
        env = {"PATH": contract.TRUSTED_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        try:
            self.process = subprocess.Popen(argv, stdin=stdin, stdout=stdout, stderr=self.errors,
                                            pass_fds=(read_end,), env=env)
        finally:
            os.close(read_end)

    def failure(self):
        self.errors.seek(0)
        text = self.errors.read(300).decode("utf-8", "replace").strip().replace("\n", " ")
        return "OpenSSL failed" + (": " + text if text else "")

    def stop(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.errors.seek(0)

    def close(self):
        """Release the child's pipes and the temporary error file."""
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
        if not self.errors.closed:
            self.errors.close()


def seal(key, path, write_tar):
    """Write HEADER + AES-256-CTR(tar) + HMAC tag to a new file; write_tar receives a binary stream."""
    salt = os.urandom(SALT_BYTES)
    passphrase, mac_key = derive(key, salt)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, MAGIC + salt)
        cipher = Cipher(passphrase, False, subprocess.PIPE, descriptor)   # appends at the shared file offset
        try:
            try:
                write_tar(cipher.process.stdin)
                cipher.process.stdin.close()
            except BrokenPipeError:
                pass
            if cipher.process.wait() != 0:
                fail(cipher.failure())
        except BaseException:
            cipher.stop()
            raise
        finally:
            cipher.close()
        mac = hmac.new(mac_key, digestmod=hashlib.sha256)
        with open(path, "rb") as written:
            for block in iter(lambda: written.read(CHUNK), b""):
                mac.update(block)
        os.write(descriptor, mac.digest())
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        os.unlink(path)
        raise
    os.close(descriptor)


def feed(path, length, sink, problems):
    try:
        with open(path, "rb") as source:
            source.seek(HEADER_BYTES)
            while length:
                block = source.read(min(CHUNK, length))
                if not block:
                    raise EOFError("archive ended early")
                sink.write(block)
                length -= len(block)
    except BaseException as error:    # recorded for the reader thread; never silently dropped
        problems.append(error)
    finally:
        try:
            sink.close()
        except OSError:
            pass


def unseal(key, path, consume):
    """Authenticate the whole file, then decrypt it into `consume(binary_stream)`."""
    size = os.path.getsize(path)
    if size < HEADER_BYTES + OPENSSL_SALTED + TAG_BYTES:
        fail("archive is truncated")
    with open(path, "rb") as source:
        header = source.read(HEADER_BYTES)
        if header[:len(MAGIC)] != MAGIC:
            fail("not a Neptune backup archive (unknown header)")
        passphrase, mac_key = derive(key, header[len(MAGIC):])
        mac, remaining = hmac.new(mac_key, header, hashlib.sha256), size - HEADER_BYTES - TAG_BYTES
        left = remaining
        while left:
            block = source.read(min(CHUNK, left))
            if not block:
                fail("archive is truncated")
            mac.update(block)
            left -= len(block)
        if not hmac.compare_digest(mac.digest(), source.read(TAG_BYTES)):
            fail("authentication failed: wrong key or modified archive")
    cipher = Cipher(passphrase, True, subprocess.PIPE, subprocess.PIPE)
    problems = []
    feeder = threading.Thread(target=feed, args=(path, remaining, cipher.process.stdin, problems), daemon=True)
    feeder.start()
    try:
        consume(cipher.process.stdout)
        while cipher.process.stdout.read(CHUNK):    # tar stops at its end marker; let openssl finish
            pass
    except BaseException:
        cipher.stop()
        raise
    finally:
        feeder.join()
        code = cipher.process.wait()
        message = cipher.failure() if code else ""
        cipher.close()
    if code != 0 or problems:
        fail(message or "could not feed the authenticated ciphertext")


# ------------------------------------------------------------ archive layout

def member_path(name):
    """A normalised relative path safe to create beneath a restore directory."""
    if (not isinstance(name, str) or not name or len(name) > MAX_NAME or name.startswith("/") or "\\" in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        fail("unsafe archive path")
    return name


def is_sqlite_name(name):
    return name.endswith(SQLITE_SUFFIXES)


def is_companion(name):
    return any(name.endswith(suffix) and is_sqlite_name(name[:-len(suffix)]) for suffix in SQLITE_COMPANIONS)


def collect(root, sources, archive_dir):
    """Plan the archive without reading file contents. Anything unsafe to restore fails now."""
    entries, seen = [], set()
    for source in sources:
        current = root
        for part in source.split("/"):
            current += "/" + part
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                fail("backup source is missing: " + source)
            if stat.S_ISLNK(st.st_mode):
                fail("symlinks are not archived: " + source)
        stack = [(source, st)]
        while stack:
            relative, st = stack.pop()
            if relative in seen or contract.inside(relative, archive_dir):
                continue
            seen.add(relative)
            member_path(relative)
            absolute = root + "/" + relative
            if stat.S_ISLNK(st.st_mode):
                fail("symlinks are not archived: " + relative)
            elif stat.S_ISDIR(st.st_mode):
                entries.append({"path": relative, "kind": "dir", "mode": stat.S_IMODE(st.st_mode), "abs": absolute})
                for name in sorted(os.listdir(absolute)):
                    if not is_companion(name):
                        stack.append((relative + "/" + name, os.lstat(absolute + "/" + name)))
            elif stat.S_ISREG(st.st_mode):
                kind = "sqlite" if is_sqlite_name(relative) else "file"
                entries.append({"path": relative, "kind": kind, "mode": stat.S_IMODE(st.st_mode), "abs": absolute})
            else:
                fail("special files are not archived: " + relative)
            if len(entries) > MAX_FILES:
                fail("too many entries; archive a narrower source")
    return sorted(entries, key=lambda entry: entry["path"])


def snapshot_database(source, scratch):
    """Consistent copy through SQLite's backup API; copying a live WAL database file is not safe."""
    with open(source, "rb") as stream:
        if stream.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
            fail("a declared database file is not an SQLite database")
    target = os.path.join(scratch, os.urandom(6).hex())
    reader = sqlite3.connect("file:%s?mode=ro" % quote(source), uri=True, timeout=30)
    try:
        writer = sqlite3.connect(target)
        try:
            reader.backup(writer)
        finally:
            writer.close()
    except sqlite3.Error as error:
        fail("database snapshot failed (%s)" % type(error).__name__)
    finally:
        reader.close()
    return target


class Digesting:
    """File-like wrapper that hashes exactly the bytes the tar writer consumes."""

    def __init__(self, stream, limit):
        self.stream, self.left, self.digest = stream, limit, hashlib.sha256()

    def read(self, size=-1):
        block = self.stream.read(self.left if size < 0 else min(size, self.left))
        self.left -= len(block)
        self.digest.update(block)
        return block


def add_entry(tar, entry, scratch, manifest):
    if entry["kind"] == "dir":
        info = tarfile.TarInfo("files/" + entry["path"])
        info.type, info.mode = tarfile.DIRTYPE, entry["mode"]
        tar.addfile(info)
        manifest["directories"].append({"path": entry["path"], "mode": entry["mode"]})
        return
    source = snapshot_database(entry["abs"], scratch) if entry["kind"] == "sqlite" else entry["abs"]
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            fail("source is not a regular file: " + entry["path"])
        info = tarfile.TarInfo("files/" + entry["path"])
        info.size, info.mode, info.mtime = before.st_size, entry["mode"], int(before.st_mtime)
        reader = Digesting(stream, before.st_size)
        tar.addfile(info, reader)
        after = os.fstat(stream.fileno())
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns) or reader.left:
            fail("source changed during the backup: " + entry["path"])
    manifest["files"].append({"path": entry["path"], "size": before.st_size, "sha256": reader.digest.hexdigest(),
                              "mode": entry["mode"]})


def write_archive(stream, entries, scratch):
    manifest = {"schema": MANIFEST_SCHEMA, "files": [], "directories": []}
    with tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for entry in entries:
            add_entry(tar, entry, scratch, manifest)
        data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        info = tarfile.TarInfo("MANIFEST.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return manifest


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------- create

def key_path(declaration):
    name = declaration["backup"]["key"]
    if name is None:
        fail("the declaration names no backup key")
    return declaration["credentials"][name]["path"]


def create(declaration, now=None):
    backup, root = declaration["backup"], declaration["root"]
    if not backup["sources"]:
        fail("the declaration lists no backup sources")
    if os.path.realpath(root) != root:
        fail("root must be a real path without symlinks")
    key = read_key(key_path(declaration))
    archive_dir = backup["archive_dir"]
    outbox = root + "/" + archive_dir
    entries = collect(root, backup["sources"], archive_dir)
    if not os.path.isdir(outbox):
        ensure_directory(os.path.dirname(outbox))
        try:
            os.mkdir(outbox, 0o700)
        except FileExistsError:
            pass
    if os.path.islink(outbox) or not private_directory(outbox):
        fail("the archive directory must be a real directory not writable by group or other")
    stamp = time.gmtime(now if now is not None else time.time())
    name = "nbk-%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", stamp), os.urandom(4).hex())
    final, partial = "%s/%s.nbk" % (outbox, name), "%s/.%s.partial" % (outbox, name)
    scratch = tempfile.mkdtemp(prefix=".snapshot-", dir=outbox)
    holder = {}
    try:
        seal(key, partial, lambda stream: holder.update(manifest=write_archive(stream, entries, scratch)))
        os.rename(partial, final)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if os.path.lexists(partial):
            os.unlink(partial)
    manifest = holder["manifest"]
    size = os.path.getsize(final)
    sidecar = {"schema": contract.SIDECAR_SCHEMA, "created_epoch": calendar_epoch(stamp),
               "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", stamp), "format": "NBK1", "archive": name + ".nbk",
               "archive_bytes": size, "archive_sha256": contract.file_sha256(final),
               "manifest_sha256": manifest_digest(manifest), "file_count": len(manifest["files"]),
               "directory_count": len(manifest["directories"]),
               "plaintext_bytes": sum(item["size"] for item in manifest["files"]),
               "sqlite_snapshots": sum(entry["kind"] == "sqlite" for entry in entries),
               "sources": list(backup["sources"]),
               "excluded": [archive_dir] if any(contract.inside(archive_dir, s) for s in backup["sources"]) else [],
               "key_fingerprint": fingerprint(key), "host_id": contract.host_id(), "tool_sha256": contract.tool_sha256()}
    contract.validate_sidecar(sidecar)
    try:
        contract.write_json("%s/%s.json" % (outbox, name), sidecar)
    except BaseException:
        os.unlink(final)
        raise
    return sidecar


def calendar_epoch(stamp):
    import calendar
    return calendar.timegm(stamp)


# -------------------------------------------------------------------- restore

def reject_symlinks(path):
    path = Path(os.path.abspath(path))
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        fail("the restore directory path must not contain symlinks")
    return str(path)


def prepare_destination(into):
    into = reject_symlinks(into)
    created = not os.path.lexists(into)
    if created:
        if not os.path.isdir(os.path.dirname(into)):
            fail("the restore directory's parent must exist")
        os.mkdir(into, 0o700)
    elif not os.path.isdir(into) or os.listdir(into):
        fail("the restore directory must be new or empty")
    return into, created


def extract_member(tar, member, destination, seen, directories):
    relative = member_path(member.name[len("files/"):]) if member.name.startswith("files/") else fail("unexpected archive member")
    if relative in seen or relative in directories:
        fail("duplicate archive member")
    target = destination + "/" + relative
    if member.isdir():
        os.makedirs(target, mode=0o700, exist_ok=True)
        directories[relative] = member.mode & 0o777
        return
    if not member.isreg():
        fail("unsupported archive member type")
    if len(seen) >= MAX_FILES:
        fail("too many archive members")
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    digest, total = hashlib.sha256(), 0
    source = tar.extractfile(member)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        for block in iter(lambda: source.read(CHUNK), b""):
            output.write(block)
            digest.update(block)
            total += len(block)
    if total != member.size:
        fail("archive member is truncated")
    seen[relative] = (total, digest.hexdigest())


def read_stream(stream, destination):
    seen, directories, manifest = {}, {}, None
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            if manifest is not None:
                fail("archive members follow the manifest")
            if member.name == "MANIFEST.json":
                if not member.isreg() or member.size > MAX_MANIFEST_BYTES:
                    fail("invalid manifest member")
                manifest = contract.strict_json(tar.extractfile(member).read(), "Archive manifest")
            else:
                extract_member(tar, member, destination, seen, directories)
    if manifest is None:
        fail("archive has no manifest")
    return manifest, seen, directories


def verify_manifest(manifest, seen, directories):
    """Every archived byte must match the hashes recorded when the files were read."""
    contract.exact(manifest, ("schema", "files", "directories"), "Archive manifest")
    if manifest["schema"] != MANIFEST_SCHEMA or not isinstance(manifest["files"], list) \
            or not isinstance(manifest["directories"], list):
        fail("unsupported manifest")
    listed = {}
    for item in manifest["files"]:
        contract.exact(item, ("path", "size", "sha256", "mode"), "Manifest file")
        if item["path"] in listed:
            fail("manifest lists a file twice")
        listed[item["path"]] = item
    if set(listed) != set(seen) or {d["path"] for d in manifest["directories"]} != set(directories):
        fail("archive contents differ from the manifest")
    for path, item in listed.items():
        if (item["size"], item["sha256"]) != seen[path]:
            fail("archived file differs from the manifest: " + path)


def check_databases(destination, manifest):
    checked = healthy = 0
    for item in manifest["files"]:
        if not is_sqlite_name(item["path"]):
            continue
        checked += 1
        connection = sqlite3.connect("file:%s?mode=ro&immutable=1" % quote(destination + "/" + item["path"]), uri=True)
        try:
            healthy += connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        except sqlite3.Error:
            pass
        finally:
            connection.close()
    return checked, healthy


def apply_modes(destination, manifest):
    for item in sorted(manifest["directories"], key=lambda d: d["path"], reverse=True):
        os.chmod(destination + "/" + item["path"], item["mode"] & 0o700)
    for item in manifest["files"]:
        os.chmod(destination + "/" + item["path"], item["mode"] & 0o700)   # owner bits only: restores are private


def clear(path):
    for name in os.listdir(path):
        child = os.path.join(path, name)
        if os.path.isdir(child) and not os.path.islink(child):
            os.chmod(child, 0o700)
            for directory, subdirectories, _files in os.walk(child):
                os.chmod(directory, 0o700)
            shutil.rmtree(child, ignore_errors=True)
        else:
            os.unlink(child)


def restore_drill(declaration, archive, sidecar_path, into, origin, keep=False, now=None):
    if origin not in ("offhost", "local"):
        fail("origin must be offhost or local")
    archive = os.path.abspath(archive)
    if os.path.islink(archive) or not os.path.isfile(archive):
        fail("the archive must be a regular file")
    value, sidecar_digest = contract.read_json(sidecar_path, contract.MAX_RECEIPT_BYTES, "Backup sidecar")
    sidecar = contract.validate_sidecar(value)
    key = read_key(key_path(declaration))
    if fingerprint(key) != sidecar["key_fingerprint"]:
        fail("this key does not match the archive's recorded key fingerprint")
    if os.path.getsize(archive) != sidecar["archive_bytes"] or contract.file_sha256(archive) != sidecar["archive_sha256"]:
        fail("the archive differs from its pre-upload record")
    destination, created = prepare_destination(into)
    if shutil.disk_usage(destination).free < sidecar["plaintext_bytes"] + SPARE_BYTES:
        fail("not enough free space to restore this archive")
    try:
        results = {}
        unseal(key, archive, lambda stream: results.update(zip(("manifest", "seen", "directories"),
                                                                 read_stream(stream, destination))))
        manifest = results["manifest"]
        verify_manifest(manifest, results["seen"], results["directories"])
        if manifest_digest(manifest) != sidecar["manifest_sha256"]:
            fail("the manifest differs from the archive record")
        if (len(manifest["files"]), len(manifest["directories"])) != (sidecar["file_count"], sidecar["directory_count"]):
            fail("file counts differ from the archive record")
        apply_modes(destination, manifest)
        checked, healthy = check_databases(destination, manifest)
        restore_id, stamp = contract.host_id(), time.gmtime(now if now is not None else time.time())
        source_id = sidecar["host_id"]
        receipt = {"schema": contract.DRILL_SCHEMA, "restored_epoch": calendar_epoch(stamp),
                   "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", stamp), "archive_sha256": sidecar["archive_sha256"],
                   "archive_bytes": sidecar["archive_bytes"], "sidecar_sha256": sidecar_digest,
                   "manifest_sha256": sidecar["manifest_sha256"], "key_fingerprint": sidecar["key_fingerprint"],
                   "file_count": sidecar["file_count"], "files_verified": len(results["seen"]),
                   "directory_count": sidecar["directory_count"],
                   "bytes_verified": sum(size for size, _ in results["seen"].values()),
                   "sqlite_checked": checked, "sqlite_ok": healthy, "origin": origin, "origin_attested": True,
                   "source_host_id": source_id, "restore_host_id": restore_id,
                   "independent_host": None if source_id is None or restore_id is None else source_id != restore_id,
                   "tool_sha256": contract.tool_sha256(), "retained": bool(keep)}
        contract.validate_drill(receipt)
        if checked != healthy:
            fail("a restored database failed its integrity check")
        receipt_path = declaration["root"] + "/" + declaration["backup"]["drill_receipt"]
        ensure_directory(os.path.dirname(receipt_path))
        contract.write_json(receipt_path, receipt, replace=True)
    except BaseException:
        if created:
            clear(destination)
            os.rmdir(destination)
        else:
            clear(destination)
        raise
    if not keep:
        clear(destination)
        if created:
            os.rmdir(destination)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("keygen", "create the declared backup key"), ("create", "write one encrypted archive and its record"),
                       ("restore-drill", "restore an archive into a new directory and record the drill")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--declaration", type=Path, required=True)
        if name == "restore-drill":
            command.add_argument("--archive", type=Path, required=True)
            command.add_argument("--sidecar", type=Path, required=True)
            command.add_argument("--into", type=Path, required=True)
            command.add_argument("--origin", choices=("offhost", "local"), required=True,
                                 help="where this copy of the archive was fetched from (attested, not verified)")
            command.add_argument("--keep", action="store_true", help="leave the restored files in place")
    args = parser.parse_args(argv)
    try:
        declaration, _ = contract.load_declaration(args.declaration)
        if args.command == "keygen":
            result = {"key_fingerprint": make_key(key_path(declaration))}
        elif args.command == "create":
            result = create(declaration)
        else:
            result = restore_drill(declaration, args.archive, args.sidecar, args.into, args.origin, args.keep)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, sqlite3.Error, tarfile.TarError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
