"""Backup and restore-drill contracts run against temporary trees and the host OpenSSL.

They establish this tool's behaviour on a synthetic tree. They do not prove that a
real research host was provisioned, that a real off-host destination exists or that
any archive was restored from one.
"""
import hashlib
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
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import host_backup as backup
import host_contract as contract

MARKER = b"neptune-research-marker-4c1f90"
KEY_FINGERPRINT_LENGTH = 16


class Tree(unittest.TestCase):
    """A synthetic research tree with a declaration, a key and a private source set."""

    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="neptune-backup-")).resolve()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.base = base
        self.root = base / "srv"
        (self.root / "state/jobs").mkdir(parents=True)
        (self.root / "private/manifests").mkdir(parents=True)
        (self.root / "state/jobs/notes.txt").write_bytes(MARKER + b"\n")
        (self.root / "private/manifests/one.json").write_text('{"a": 1}\n')
        connection = sqlite3.connect(self.root / "state/jobs/jobs.sqlite")
        connection.execute("create table jobs (id integer primary key, name text)")
        connection.execute("insert into jobs (name) values ('one')")
        connection.commit()
        connection.close()
        self.key_dir = base / "etc/neptune/coordinator"
        self.key_dir.mkdir(parents=True)
        os.chmod(self.key_dir, 0o700)
        self.key_path = self.key_dir / "backup.key"
        self.declaration = self.make_declaration()

    def make_declaration(self):
        declaration = contract.template()
        declaration["root"] = str(self.root)
        declaration["backup"]["sources"] = ["state", "private/manifests"]
        declaration["credentials"]["backup-key"]["path"] = str(self.key_path)
        declaration["backup"]["max_age_seconds"] = 7 * 86400
        return contract.validate(declaration)

    def keygen(self):
        return backup.make_key(self.key_path)

    def create(self, declaration=None):
        return backup.create(declaration or self.declaration)

    def archive_paths(self, sidecar):
        outbox = self.root / self.declaration["backup"]["archive_dir"]
        return outbox / sidecar["archive"], outbox / (sidecar["archive"][:-4] + ".json")

    def drill(self, archive, sidecar_path, into, origin="offhost", keep=False, declaration=None):
        return backup.restore_drill(declaration or self.declaration, archive, sidecar_path, into, origin, keep)


class KeyTests(Tree):
    def test_keygen_creates_a_private_key_and_never_replaces_one(self):
        fingerprint = self.keygen()
        self.assertEqual(len(fingerprint), KEY_FINGERPRINT_LENGTH)
        self.assertEqual(stat.S_IMODE(self.key_path.stat().st_mode), 0o600)
        self.assertEqual(len(self.key_path.read_text().strip()), 64)
        with self.assertRaises(backup.BackupError) as caught:
            self.keygen()
        self.assertIn("never replaced", str(caught.exception))

    def test_keygen_creates_the_missing_parent_directories_privately(self):
        self.key_dir.rmdir()
        self.keygen()
        self.assertTrue(self.key_path.is_file())
        self.assertEqual(stat.S_IMODE(self.key_dir.stat().st_mode), 0o700)

    def test_an_insecure_key_file_is_refused_rather_than_used(self):
        self.keygen()
        os.chmod(self.key_path, 0o644)
        with self.assertRaises(backup.BackupError) as caught:
            backup.read_key(self.key_path)
        self.assertIn("mode 0600", str(caught.exception))
        os.chmod(self.key_path, 0o600)
        self.key_path.unlink()
        with self.assertRaises(backup.BackupError) as caught:
            backup.read_key(self.key_path)
        self.assertIn("missing", str(caught.exception))

    def test_a_key_in_a_shared_directory_is_refused(self):
        self.keygen()
        os.chmod(self.key_dir, 0o770)
        with self.assertRaises(backup.BackupError) as caught:
            backup.read_key(self.key_path)
        self.assertIn("writable by group or other", str(caught.exception))

    def test_a_file_or_symlink_in_the_way_of_a_directory_is_refused(self):
        blocker = self.base / "etc/neptune/blocker"
        blocker.write_text("x")
        with self.assertRaises(backup.BackupError) as caught:
            backup.ensure_directory(str(blocker))
        self.assertIn("not a directory", str(caught.exception))
        link = self.base / "etc/neptune/link"
        os.symlink(self.base, link)
        with self.assertRaises(backup.BackupError) as caught:
            backup.ensure_directory(str(link / "child"))
        self.assertIn("symlinked", str(caught.exception))

    def test_hkdf_matches_the_rfc_5869_test_vector(self):
        secret = bytes([0x0b]) * 22
        salt = bytes(range(13))
        info = bytes(range(0xf0, 0xfa))
        self.assertEqual(backup.hkdf(secret, salt, info, 42).hex(),
                         "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865")
        self.assertEqual(backup.hkdf(secret, salt, info, 42), backup.hkdf(secret, salt, info, 42))
        self.assertNotEqual(backup.hkdf(secret, salt, info, 42), backup.hkdf(secret, salt, b"other", 42))


class ArchiveTests(Tree):
    def setUp(self):
        super().setUp()
        self.keygen()
        self.sidecar = self.create()
        self.archive, self.sidecar_path = self.archive_paths(self.sidecar)

    def test_an_archive_records_its_identity_and_keeps_the_source_plaintext_out_of_the_file(self):
        contract.validate_sidecar(self.sidecar)
        self.assertTrue(self.archive.is_file())
        self.assertEqual(self.sidecar["archive_bytes"], self.archive.stat().st_size)
        self.assertEqual(self.sidecar["archive_sha256"], contract.file_sha256(self.archive))
        self.assertEqual(self.sidecar["key_fingerprint"], backup.fingerprint(backup.read_key(self.key_path)))
        self.assertEqual(self.sidecar["file_count"], 3)
        self.assertEqual(self.sidecar["sqlite_snapshots"], 1)
        self.assertEqual(self.sidecar["excluded"], ["state/backup/outbox"])
        self.assertNotIn(MARKER, self.archive.read_bytes())
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o600)

    def test_the_archive_directory_is_private_and_holds_one_record_per_archive(self):
        outbox = self.root / self.declaration["backup"]["archive_dir"]
        self.assertEqual(stat.S_IMODE(outbox.stat().st_mode), 0o700)
        names = sorted(path.name for path in outbox.iterdir())
        self.assertEqual(names, sorted([self.sidecar["archive"], self.sidecar["archive"][:-4] + ".json"]))

    def test_a_missing_source_fails_instead_of_producing_a_partial_archive(self):
        shutil.rmtree(self.root / "private/manifests")
        with self.assertRaises(backup.BackupError) as caught:
            self.create()
        self.assertIn("missing", str(caught.exception))

    def test_symlinks_and_special_files_are_never_archived(self):
        os.symlink(self.root / "state/jobs/notes.txt", self.root / "state/jobs/link")
        with self.assertRaises(backup.BackupError) as caught:
            self.create()
        self.assertIn("symlink", str(caught.exception))
        os.unlink(self.root / "state/jobs/link")
        os.mkfifo(self.root / "state/jobs/pipe")
        with self.assertRaises(backup.BackupError) as caught:
            self.create()
        self.assertIn("special file", str(caught.exception))

    def test_the_passphrase_never_reaches_argv_or_the_environment(self):
        calls = []
        original = subprocess.Popen

        def record(argv, **kwargs):
            calls.append((list(argv), dict(kwargs.get("env") or {})))
            return original(argv, **kwargs)

        with patch("subprocess.Popen", record):
            self.create()
        self.assertTrue(calls)
        key = backup.read_key(self.key_path)
        salt = self.archive.read_bytes()[len(backup.MAGIC):backup.HEADER_BYTES]
        passphrase, mac_key = backup.derive(key, salt)
        for argv, environment in calls:
            self.assertIn("-pass", argv)
            self.assertTrue(any(item.startswith("fd:") for item in argv), argv)
            self.assertNotIn("pass:stdin", " ".join(argv))
            joined = " ".join(str(item) for item in argv) + "".join(str(value) for value in environment.values())
            for secret in (key.hex(), passphrase.decode(), mac_key.hex()):
                self.assertNotIn(secret, joined)

    def test_the_manifest_lists_every_archived_file_and_matches_the_record(self):
        manifest = json.loads(self._manifest_bytes())
        self.assertEqual(manifest["schema"], backup.MANIFEST_SCHEMA)
        self.assertEqual({item["path"] for item in manifest["files"]},
                         {"state/jobs/notes.txt", "state/jobs/jobs.sqlite", "private/manifests/one.json"})
        self.assertEqual(backup.manifest_digest(manifest), self.sidecar["manifest_sha256"])

    def _manifest_bytes(self):
        holder = {}

        def consume(stream):
            manifest, seen, directories = backup.read_stream(stream, str(self.base / "scratch"))
            holder.update(manifest=manifest, seen=seen, directories=directories)

        (self.base / "scratch").mkdir(exist_ok=True)
        backup.unseal(backup.read_key(self.key_path), self.archive, consume)
        return json.dumps(holder["manifest"])


class RestoreTests(Tree):
    def setUp(self):
        super().setUp()
        self.keygen()
        self.sidecar = self.create()
        self.archive, self.sidecar_path = self.archive_paths(self.sidecar)

    def test_a_drill_restores_every_file_and_records_the_verified_result(self):
        destination = self.base / "restored"
        receipt = self.drill(self.archive, self.sidecar_path, destination, keep=True)
        contract.validate_drill(receipt)
        self.assertEqual(receipt["files_verified"], self.sidecar["file_count"])
        self.assertEqual(receipt["sqlite_checked"], receipt["sqlite_ok"])
        self.assertEqual(receipt["origin"], "offhost")
        self.assertTrue(receipt["origin_attested"])
        for relative in ("state/jobs/notes.txt", "private/manifests/one.json"):
            self.assertEqual(hashlib.sha256((destination / relative).read_bytes()).hexdigest(),
                             hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), relative)
        restored = sqlite3.connect(destination / "state/jobs/jobs.sqlite")
        try:
            self.assertEqual(restored.execute("select name from jobs").fetchall(), [("one",)])
        finally:
            restored.close()
        stored = json.loads((self.root / self.declaration["backup"]["drill_receipt"]).read_text())
        self.assertEqual(stored["archive_sha256"], receipt["archive_sha256"])

    def test_a_restored_database_is_readable_and_holds_the_source_rows(self):
        destination = self.base / "restored"
        self.drill(self.archive, self.sidecar_path, destination, keep=True)
        connection = sqlite3.connect(destination / "state/jobs/jobs.sqlite")
        try:
            self.assertEqual(connection.execute("select name from jobs").fetchall(), [("one",)])
        finally:
            connection.close()

    def test_the_restored_copy_is_private_and_removed_unless_kept(self):
        destination = self.base / "restored"
        self.drill(self.archive, self.sidecar_path, destination)
        self.assertFalse(destination.exists())
        self.drill(self.archive, self.sidecar_path, destination, keep=True)
        self.assertEqual(stat.S_IMODE((destination / "state/jobs/notes.txt").stat().st_mode), 0o600)

    def test_tampered_ciphertext_fails_authentication_and_leaves_no_restored_files(self):
        data = bytearray(self.archive.read_bytes())
        data[len(data) // 2] ^= 0xFF
        tampered = self.base / "tampered.nbk"
        tampered.write_bytes(bytes(data))
        record = json.loads(self.sidecar_path.read_text())
        record["archive_bytes"] = tampered.stat().st_size
        record["archive_sha256"] = contract.file_sha256(tampered)
        record_path = self.base / "tampered.json"
        record_path.write_text(json.dumps(record))
        destination = self.base / "restored"
        with self.assertRaises(backup.BackupError) as caught:
            self.drill(tampered, record_path, destination, keep=True)
        self.assertIn("authentication failed", str(caught.exception))
        self.assertFalse(destination.exists())

    def test_an_archive_that_differs_from_its_record_is_refused_before_decryption(self):
        other = self.base / "other.nbk"
        other.write_bytes(self.archive.read_bytes() + b"extra")
        with self.assertRaises(backup.BackupError) as caught:
            self.drill(other, self.sidecar_path, self.base / "restored")
        self.assertIn("differs from its pre-upload record", str(caught.exception))

    def test_a_drill_with_a_different_key_is_refused(self):
        other = self.base / "other.key"
        other.write_bytes(os.urandom(32).hex().encode() + b"\n")
        os.chmod(other, 0o600)
        declaration = json.loads(json.dumps(self.declaration))
        declaration["credentials"]["backup-key"]["path"] = str(other)
        with self.assertRaises(backup.BackupError) as caught:
            self.drill(self.archive, self.sidecar_path, self.base / "restored", declaration=declaration)
        self.assertIn("key fingerprint", str(caught.exception))

    def test_a_wrong_key_cannot_decrypt_the_archive(self):
        with self.assertRaises(backup.BackupError) as caught:
            backup.unseal(os.urandom(32), self.archive, lambda stream: stream.read(1))
        self.assertIn("authentication failed", str(caught.exception))

    def test_a_truncated_or_foreign_file_is_not_an_archive(self):
        truncated = self.base / "truncated.nbk"
        truncated.write_bytes(self.archive.read_bytes()[:20])
        with self.assertRaises(backup.BackupError) as caught:
            backup.unseal(backup.read_key(self.key_path), truncated, lambda stream: stream.read(1))
        self.assertIn("truncated", str(caught.exception))
        foreign = self.base / "foreign.nbk"
        foreign.write_bytes(b"ustar" + bytes(200))
        with self.assertRaises(backup.BackupError) as caught:
            backup.unseal(backup.read_key(self.key_path), foreign, lambda stream: stream.read(1))
        self.assertIn("unknown header", str(caught.exception))

    def test_an_unsafe_archive_member_is_refused_before_anything_is_written(self):
        for name in ("../escape", "/absolute", "state/../../escape", "state//double", ""):
            with self.subTest(name):
                with self.assertRaises(backup.BackupError):
                    backup.member_path(name)

    def test_a_symlink_member_is_not_restored(self):
        buffer = tempfile.TemporaryFile()
        self.addCleanup(buffer.close)
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo("files/state/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        buffer.seek(0)
        destination = self.base / "restored"
        destination.mkdir()
        with self.assertRaises(backup.BackupError) as caught:
            backup.read_stream(buffer, str(destination))
        self.assertIn("unsupported archive member type", str(caught.exception))

    def test_a_restore_into_a_used_or_symlinked_directory_is_refused(self):
        used = self.base / "used"
        used.mkdir()
        (used / "existing.txt").write_text("x")
        with self.assertRaises(backup.BackupError) as caught:
            self.drill(self.archive, self.sidecar_path, used)
        self.assertIn("new or empty", str(caught.exception))
        link = self.base / "link"
        os.symlink(self.base, link)
        with self.assertRaises(backup.BackupError) as caught:
            self.drill(self.archive, self.sidecar_path, link / "restored")
        self.assertIn("symlink", str(caught.exception))

    def test_the_drill_receipt_is_replaced_and_never_leaves_a_stale_result(self):
        path = self.root / self.declaration["backup"]["drill_receipt"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema": "stale"}')
        self.drill(self.archive, self.sidecar_path, self.base / "restored")
        receipt = json.loads(path.read_text())
        contract.validate_drill(receipt)
        self.assertEqual(receipt["archive_sha256"], self.sidecar["archive_sha256"])


class CommandLineTests(Tree):
    def test_the_commands_report_failure_without_writing_a_result(self):
        declaration = self.base / "declaration.json"
        declaration.write_text(json.dumps(self.declaration))
        script = str(Path(backup.__file__).resolve())
        keygen = subprocess.run([sys.executable, script, "keygen", "--declaration", str(declaration)],
                                capture_output=True, text=True)
        self.assertEqual(keygen.returncode, 0, keygen.stderr)
        self.assertEqual(len(json.loads(keygen.stdout)["key_fingerprint"]), KEY_FINGERPRINT_LENGTH)
        created = subprocess.run([sys.executable, script, "create", "--declaration", str(declaration)],
                                 capture_output=True, text=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        sidecar = json.loads(created.stdout)
        archive, sidecar_path = self.archive_paths(sidecar)
        drill = subprocess.run([sys.executable, script, "restore-drill", "--declaration", str(declaration),
                                "--archive", str(archive), "--sidecar", str(sidecar_path),
                                "--into", str(self.base / "restored"), "--origin", "offhost"],
                               capture_output=True, text=True)
        self.assertEqual(drill.returncode, 0, drill.stderr)
        self.assertEqual(json.loads(drill.stdout)["files_verified"], sidecar["file_count"])
        broken = self.base / "broken.json"
        broken.write_text('{"schema": "x"}')
        failed = subprocess.run([sys.executable, script, "create", "--declaration", str(broken)],
                                capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertTrue(failed.stderr.startswith("FAIL: "))


if __name__ == "__main__":
    unittest.main()
