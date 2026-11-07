"""Host readiness contracts use simulated accounts, mounts and services on temporary
directories. They establish the reporter's behaviour, not the state of any real host."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import host_contract as contract
import host_readiness as readiness
import verify

COORDINATOR, WORKER = 4101, 4102
CANARY = "CANARY-credential-content-7f3a91"
MACHINE_ID = "0123456789abcdef0123456789abcdef"
CLOCK = 1_800_000_000.0
COORD_NAME, WORKER_NAME = "svc-neptune-9x", "svc-worker-9x"
OPENED = []
WATCHED = set()


def audit(event, arguments):
    """Permanent but inert unless a test names a path: records every open() of it."""
    if event == "open" and WATCHED and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
        if os.fsdecode(arguments[0]) in WATCHED:
            OPENED.append(os.fsdecode(arguments[0]))


sys.addaudithook(audit)


def account(uid, groups=(), home=None):
    return {"uid": uid, "gid": uid, "home": home or "/home/sim-%d" % uid, "gids": {uid}, "groups": {"sim-%d" % uid, *groups}}


UNITS = ("neptune-coordinator.service loaded active running Neptune coordinator\n"
         "private-other-project.service loaded active running Another private project\n"
         "ssh.service loaded active running OpenBSD Secure Shell server\n")


class FakeProbe(readiness.Probe):
    """Real temporary files with simulated ownership; nothing outside the base is ever touched."""

    def __init__(self, base):
        self.base = str(base)
        self.owners, self.virtual, self.denied, self.executed = {}, {}, set(), []
        self.texts = {"/etc/os-release": 'ID=debian\nVERSION_ID="13"\nPRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n',
                      "/proc/meminfo": "MemTotal:  8000000 kB\nMemAvailable:  5000000 kB\nSwapTotal:  1000000 kB\n",
                      "/etc/machine-id": MACHINE_ID + "\n", "/proc/self/mountinfo": ""}
        self.accounts = {COORD_NAME: account(COORDINATOR), WORKER_NAME: account(WORKER)}
        self.programs = {name: "/usr/bin/" + name for name in
                         ("git", "openssl", "cc", "make", "c++", "Xvfb", "docker", "ffmpeg", "rclone", "systemctl", "python3")}
        self.commands = {("git", "--version"): (0, "git version 2.47.3\n", ""),
                         ("openssl", "version"): (0, "OpenSSL 3.5.7 9 Jun 2026\n", ""),
                         ("cc", "--version"): (0, "cc (Debian 14.2.0-19) 14.2.0\n", ""),
                         ("make", "--version"): (0, "GNU Make 4.4.1\n", ""),
                         ("c++", "--version"): (0, "c++ (Debian 14.2.0-19) 14.2.0\n", ""),
                         ("Xvfb", "-version"): (0, "", "X.Org X Server 21.1.16\n"),
                         ("docker", "--version"): (0, "Docker version 28.0.1\n", ""),
                         ("ffmpeg", "-version"): (0, "ffmpeg version 7.1\n", ""),
                         ("systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--plain",
                          "--no-pager"): (0, UNITS, "")}
        self.system_facts = {"system": "Linux", "machine": "x86_64", "kernel": "6.12.0-test"}
        self.python_version = (3, 13, 5)
        self.clock = CLOCK

    def under(self, path):
        return path == self.base or path.startswith(self.base + "/")

    def owner_of(self, path):
        best = max((key for key in self.owners if path == key or path.startswith(key + "/")), key=len, default=None)
        return self.owners[best] if best else (COORDINATOR, COORDINATOR)

    def lstat(self, path):
        if path in self.denied:
            raise PermissionError(path)
        if path in self.virtual:
            return self.virtual[path]
        if not self.under(path):
            return None
        try:
            real = os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return None
        uid, gid = self.owner_of(path)
        return SimpleNamespace(st_mode=real.st_mode, st_uid=uid, st_gid=gid, st_size=real.st_size, st_dev=real.st_dev,
                               st_ino=real.st_ino)

    def listdir(self, path):
        if path in self.denied:
            raise PermissionError(path)
        if not self.under(path):
            raise FileNotFoundError(path)
        return sorted(os.listdir(path))

    def realpath(self, path):
        return os.path.realpath(path) if self.under(path) else path

    def read_text(self, path, limit=1 << 20):
        if path in self.texts:
            return self.texts[path]
        return super().read_text(path, limit) if self.under(path) else None

    def read_head(self, path, size):
        return super().read_head(path, size) if self.under(path) else None

    def disk_usage(self, path):
        return 100 * 1024**3, 40 * 1024**3

    def account(self, name):
        return copy.deepcopy(self.accounts.get(name))

    def which(self, name):
        return self.programs.get(name)

    def run(self, argv, timeout=8):
        self.executed.append(list(argv))
        return self.commands.get((os.path.basename(argv[0]), *argv[1:]))

    def system(self):
        return dict(self.system_facts)

    def cpus(self):
        return 4, 3

    def python(self):
        return self.python_version

    def now(self):
        return self.clock


class Host:
    """A fully provisioned simulated host that individual tests then damage."""

    def __init__(self, test):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        self.base = Path(os.path.realpath(temp.name))
        test.addCleanup(self.make_removable)   # runs before temp.cleanup
        self.root, self.repo = self.base / "neptune", self.base / "repo"
        self.probe = FakeProbe(self.base)
        self.repo.mkdir()
        self.probe.commands[("git", "-C", str(self.repo), "rev-parse", "HEAD")] = (0, "a" * 40 + "\n", "")
        self.layout()
        self.credentials()
        self.decl = self.declaration()

    def make_removable(self):
        for directory, names, _files in os.walk(self.base):
            os.chmod(directory, 0o700)

    def put(self, relative, mode, data=None, owner=None):
        path = self.root / relative
        if data is None:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.chmod(path, mode)
        if owner:
            self.probe.owners[str(path)] = owner
        return path

    def layout(self):
        self.root.mkdir()
        os.chmod(self.root, 0o755)
        for name, mode, owner in (("repos", 0o750, None), ("state", 0o700, None), ("workspaces", 0o700, (WORKER, WORKER)),
                                  ("private", 0o700, None)):
            self.put(name, mode, owner=owner)
        for name in ("disc", "bios", "power"):
            self.put("private/%s/image.bin" % name, 0o400, b"synthetic media, not a disc")
            os.chmod(self.root / "private" / name, 0o500)
        for name in ("emulator", "settings", "manifests", "captures"):
            self.put("private/%s/item.json" % name, 0o600, b"{}")
        lines = ["25 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw"]
        for index, name in enumerate(("disc", "bios", "power")):
            lines.append("%d 25 8:1 /media/%d %s ro,relatime - ext4 /dev/sda1 rw" % (40 + index, index, self.root / "private" / name))
        self.probe.texts["/proc/self/mountinfo"] = "\n".join(lines) + "\n"

    def credentials(self):
        for relative, uid in (("coordinator/github-app.pem", COORDINATOR), ("worker/github-token", WORKER),
                              ("coordinator/provider-key", COORDINATOR), ("coordinator/backup.key", COORDINATOR)):
            path = self.base / "etc/neptune" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(CANARY + "\n")
            os.chmod(path, 0o600)
            os.chmod(path.parent, 0o700)
            self.probe.owners[str(path)] = self.probe.owners[str(path.parent)] = (uid, uid)

    def declaration(self):
        declaration = contract.template()
        declaration["root"] = str(self.root)
        declaration["roles"] = {"coordinator": COORD_NAME, "worker": WORKER_NAME}
        for item in declaration["credentials"].values():
            item["path"] = str(self.base) + item["path"]
        declaration["policy"] = {"max_concurrent_jobs": 2, "max_concurrent_heavy_jobs": 1,
                                 "spend": {"currency": "USD", "daily_cap": 10, "monthly_cap": 200, "paid_fallback_allowed": False}}
        declaration["backup"]["max_age_seconds"] = 7 * 86400
        return contract.validate(declaration)

    def credential(self, name):
        return Path(self.decl["credentials"][name]["path"])

    def report(self, declaration=None):
        return readiness.build_report(declaration or self.decl, "d" * 64, self.probe, repo_root=str(self.repo))

    def checks(self, declaration=None):
        return {item["id"]: item for item in self.report(declaration)["checks"]}

    def write_backup(self, age=3600, drill_age=1800, origin="offhost", independent=True, **drill):
        outbox = self.root / self.decl["backup"]["archive_dir"]
        outbox.mkdir(parents=True, exist_ok=True)
        created = int(CLOCK - age)
        name = "nbk-%s-ab12cd34" % time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(created))
        (outbox / (name + ".nbk")).write_bytes(b"NEPTUNE-NBK1\n" + b"\x00" * 64)
        sidecar = {"schema": contract.SIDECAR_SCHEMA, "created_epoch": created,
                   "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created)), "format": "NBK1",
                   "archive": name + ".nbk", "archive_bytes": 13 + 64, "archive_sha256": "1" * 64,
                   "manifest_sha256": "2" * 64, "file_count": 5, "directory_count": 2, "plaintext_bytes": 1000,
                   "sqlite_snapshots": 1, "sources": ["state"], "excluded": [], "key_fingerprint": "3" * 16,
                   "host_id": "4" * 64, "tool_sha256": "5" * 64}
        (outbox / (name + ".json")).write_text(json.dumps(sidecar))
        restored = int(CLOCK - drill_age)
        receipt = {"schema": contract.DRILL_SCHEMA, "restored_epoch": restored,
                   "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(restored)),
                   "archive_sha256": "1" * 64, "archive_bytes": 77, "sidecar_sha256": "6" * 64, "manifest_sha256": "2" * 64,
                   "key_fingerprint": "3" * 16, "file_count": 5, "files_verified": 5, "directory_count": 2,
                   "bytes_verified": 1000, "sqlite_checked": 1, "sqlite_ok": 1, "origin": origin, "origin_attested": True,
                   "source_host_id": "4" * 64, "restore_host_id": "7" * 64 if independent else "4" * 64,
                   "independent_host": independent, "tool_sha256": "5" * 64, "retained": False}
        receipt.update(drill)
        path = self.root / self.decl["backup"]["drill_receipt"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt))
        return outbox / (name + ".nbk"), outbox / (name + ".json"), path


class DeclarationTests(unittest.TestCase):
    def test_template_is_valid_and_leaves_every_limit_and_account_unconfigured(self):
        template = contract.template()
        contract.validate(template)
        self.assertEqual(template["roles"], {"coordinator": None, "worker": None})
        self.assertEqual(template["policy"]["max_concurrent_jobs"], None)
        self.assertEqual(set(template["policy"]["spend"].values()), {None})
        self.assertIsNone(template["backup"]["max_age_seconds"])
        # The documented layout is the REQUIREMENTS.md storage layout.
        paths = {item["path"] for item in template["inputs"].values()}
        self.assertEqual(paths, {"private/" + name for name in ("disc", "bios", "power", "emulator", "settings", "manifests", "captures")})

    def test_unknown_missing_and_mistyped_fields_are_rejected(self):
        def mutate(change):
            value = contract.template()
            change(value)
            return value

        cases = {
            "unknown top-level": lambda v: v.update(extra=1),
            "missing section": lambda v: v.pop("policy"),
            "wrong schema": lambda v: v.update(schema="neptune.factory-host-declaration.v0"),
            "unknown role": lambda v: v["roles"].update(auditor="x"),
            "bad account": lambda v: v["roles"].update(worker="Root User"),
            "relative root": lambda v: v.update(root="srv/neptune"),
            "root slash": lambda v: v.update(root="/"),
            "dotdot root": lambda v: v.update(root="/srv/../etc"),
            "dotdot input": lambda v: v["inputs"]["saturn-disc"].update(path="private/../disc"),
            "absolute input": lambda v: v["inputs"]["saturn-disc"].update(path="/private/disc"),
            "backslash path": lambda v: v["inputs"]["saturn-disc"].update(path="private\\disc"),
            "control char path": lambda v: v["inputs"]["saturn-disc"].update(path="private/di\nsc"),
            "media without enforcement": lambda v: v["inputs"]["saturn-disc"].update(enforcement=None),
            "private with enforcement": lambda v: v["inputs"]["captures"].update(enforcement="mount"),
            "unknown capability": lambda v: v["inputs"]["saturn-disc"].update(needed_for=["world-domination"]),
            "relative credential": lambda v: v["credentials"]["backup-key"].update(path="etc/backup.key"),
            "duplicate credential path": lambda v: v["credentials"]["github-worker"].update(
                path=v["credentials"]["github-coordinator"]["path"]),
            "unknown credential kind": lambda v: v["credentials"]["backup-key"].update(kind="password"),
            "backup key not a backup credential": lambda v: v["backup"].update(key="github-worker"),
            "backup key unknown": lambda v: v["backup"].update(key="nothing"),
            "concurrency zero": lambda v: v["policy"].update(max_concurrent_jobs=0),
            "concurrency huge": lambda v: v["policy"].update(max_concurrent_jobs=65),
            "concurrency float": lambda v: v["policy"].update(max_concurrent_jobs=1.5),
            "concurrency bool": lambda v: v["policy"].update(max_concurrent_jobs=True),
            "concurrency text": lambda v: v["policy"].update(max_concurrent_jobs="2"),
            "heavy exceeds total": lambda v: v["policy"].update(max_concurrent_jobs=1, max_concurrent_heavy_jobs=2),
            "negative cap": lambda v: v["policy"]["spend"].update(daily_cap=-1),
            "text cap": lambda v: v["policy"]["spend"].update(daily_cap="5"),
            "infinite cap": lambda v: v["policy"]["spend"].update(daily_cap=float("inf")),
            "nan cap": lambda v: v["policy"]["spend"].update(monthly_cap=float("nan")),
            "daily above monthly": lambda v: v["policy"]["spend"].update(daily_cap=50, monthly_cap=10),
            "lowercase currency": lambda v: v["policy"]["spend"].update(currency="usd"),
            "fallback not boolean": lambda v: v["policy"]["spend"].update(paid_fallback_allowed="no"),
            "age too small": lambda v: v["backup"].update(max_age_seconds=60),
            "watch pattern with slash": lambda v: v["services"].update(watch=["../x.service"]),
            "watch not a list": lambda v: v["services"].update(watch="neptune-*"),
        }
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(contract.DeclarationError):
                contract.validate(mutate(change))

    def test_layout_cannot_expose_inputs_to_workers_or_back_up_media_and_credentials(self):
        def mutate(change):
            value = contract.template()
            change(value)
            return value

        cases = {
            "input inside workspaces": lambda v: v["inputs"]["saturn-disc"].update(path="workspaces/disc"),
            "input inside repos": lambda v: v["inputs"]["captures"].update(path="repos/captures"),
            "nested inputs": lambda v: v["inputs"]["saturn-bios"].update(path="private/disc/bios"),
            "duplicate input paths": lambda v: v["inputs"]["saturn-bios"].update(path="private/disc"),
            "input equals state": lambda v: v["inputs"]["captures"].update(path="state"),
            "source contains media": lambda v: v["backup"]["sources"].append("private"),
            "source is media": lambda v: v["backup"]["sources"].append("private/disc"),
            "source inside repos": lambda v: v["backup"]["sources"].append("repos/neptune"),
            "source inside workspaces": lambda v: v["backup"]["sources"].append("workspaces"),
            "source is archive dir": lambda v: v["backup"]["sources"].append("state/backup/outbox"),
            "source inside archive dir": lambda v: v["backup"]["sources"].append("state/backup/outbox/old"),
            "source would archive a credential": lambda v: (
                v["credentials"]["backup-key"].update(path="/srv/neptune/private/settings/backup.key")),
        }
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(contract.DeclarationError):
                contract.validate(mutate(change))
        # A source may contain the archive directory; it is skipped during backup.
        value = contract.template()
        self.assertIn("state", value["backup"]["sources"])
        contract.validate(value)

    def test_declaration_file_must_be_bounded_strict_json_without_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(os.path.realpath(directory))
            good = base / "declaration.json"
            good.write_text(json.dumps(contract.template()))
            value, digest = contract.load_declaration(good)
            self.assertEqual(value["schema"], contract.SCHEMA)
            self.assertEqual(len(digest), 64)
            payloads = {"duplicate key": '{"schema": "a", "schema": "b"}',
                        "nan": json.dumps(contract.template()).replace("null", "NaN", 1),
                        "not an object": "[]", "not json": "{", "oversized": " " * (contract.MAX_DECLARATION_BYTES + 1)}
            for name, text in payloads.items():
                path = base / (name.replace(" ", "-") + ".json")
                path.write_text(text)
                with self.subTest(name), self.assertRaises(contract.DeclarationError):
                    contract.load_declaration(path)
            link = base / "link.json"
            link.symlink_to(good)
            with self.assertRaises(contract.DeclarationError):
                contract.load_declaration(link)
            (base / "dir-link").symlink_to(base)
            with self.assertRaises(contract.DeclarationError):
                contract.load_declaration(base / "dir-link" / "declaration.json")
            with self.assertRaises(contract.MissingFile):
                contract.load_declaration(base / "missing.json")

    def test_machine_identity_is_a_one_way_hash(self):
        identity = contract.host_id_from(MACHINE_ID)
        self.assertEqual(len(identity), 64)
        self.assertNotIn(MACHINE_ID, identity)
        self.assertEqual(identity, contract.host_id_from(MACHINE_ID + "\n"))
        self.assertIsNone(contract.host_id_from(""))
        self.assertIsNone(contract.host_id_from(None))


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.host = Host(self)

    def test_provisioned_fixture_passes_static_checks_yet_leaves_live_facts_unverified(self):
        self.host.write_backup()
        report = self.host.report()
        summary, checks = report["summary"], {item["id"]: item for item in report["checks"]}
        self.assertEqual(summary["blocking"], [])
        self.assertEqual(summary["static_checks"], "pass")
        self.assertEqual(summary["factory_health"], "not-assessed")
        self.assertEqual(report["schema"], readiness.SCHEMA)
        self.assertEqual(report["identity"]["declaration_sha256"], "d" * 64)
        self.assertEqual(report["identity"]["repository_head"], "a" * 40)
        self.assertEqual(len(report["identity"]["tool_sha256"]), 64)
        for name in ("credential.github-coordinator", "credential.provider-coordinator", "credential.separation",
                     "policy.concurrency", "policy.spend", "backup.offhost"):
            self.assertEqual(checks[name]["status"], "present-unverified", name)
        for name in ("layout.root", "layout.state", "identity.separation", "input.saturn-disc.protection",
                     "backup.configuration", "backup.archive", "backup.restore-drill", "software.git"):
            self.assertEqual(checks[name]["status"], "ok", name)
        self.assertIn("credential validity, scopes, billing and quota", summary["never_verified_by_this_report"])
        self.assertIn("backup.offhost", summary["unverified"])
        self.assertEqual(summary["capabilities"]["saturn-experiments"]["state"], "static-checks-pass")
        self.assertEqual(self.host.report(), report)

    def test_absent_media_and_provider_credentials_are_reported_apart_from_installed_software(self):
        host = self.host
        for name in ("disc", "bios"):
            os.chmod(host.root / "private" / name, 0o700)
        shutil.rmtree(host.root / "private/disc")
        (host.root / "private/bios/image.bin").unlink()
        host.credential("provider-coordinator").unlink()
        report = host.report()
        checks, summary = {c["id"]: c for c in report["checks"]}, report["summary"]
        self.assertEqual(checks["input.saturn-disc.present"]["status"], "absent")
        self.assertEqual(checks["input.saturn-disc.protection"]["status"], "not-applicable")
        self.assertEqual(checks["input.saturn-bios.present"]["status"], "absent")
        self.assertEqual(checks["credential.provider-coordinator"]["status"], "absent")
        self.assertEqual(checks["software.git"]["status"], "ok")
        absent = summary["absent_by_category"]
        self.assertIn("input.saturn-disc.present", absent["input"])
        self.assertIn("credential.provider-coordinator", absent["credential"])
        self.assertNotIn("software", absent)
        self.assertIn("git", summary["installed_software"])
        self.assertEqual(summary["capabilities"]["saturn-experiments"]["state"], "blocked")
        self.assertEqual(summary["capabilities"]["provider-jobs"]["state"], "blocked")
        # Missing Saturn media blocks only Saturn experiments, not offline verification or Power work.
        self.assertEqual(summary["capabilities"]["offline-verification"]["state"], "static-checks-pass")
        self.assertEqual(summary["capabilities"]["power-experiments"]["state"], "static-checks-pass")
        self.assertEqual(summary["static_checks"], "fail")

    def test_unprovisioned_host_reports_every_prerequisite_absent_from_the_template(self):
        host = self.host
        declaration = contract.template()
        declaration["root"] = str(host.base / "unprovisioned")
        for item in declaration["credentials"].values():
            item["path"] = str(host.base) + item["path"]
        shutil.rmtree(host.base / "etc")
        checks = host.checks(contract.validate(declaration))
        for name in ("layout.root", "layout.repos", "layout.state", "layout.workspaces", "identity.coordinator",
                     "identity.worker", "policy.concurrency", "policy.spend", "credential.github-coordinator",
                     "credential.backup-key", "credential.separation", "backup.configuration", "backup.archive",
                     "backup.restore-drill", "backup.offhost", "input.saturn-disc.present", "input.captures.present"):
            self.assertEqual(checks[name]["status"], "absent", name)
        self.assertEqual(checks["policy.spend"]["detail"],
                         "not configured: currency, daily_cap, monthly_cap, paid_fallback_allowed")
        self.assertEqual(checks["software.git"]["status"], "ok")
        report = host.report(contract.validate(declaration))
        self.assertEqual(report["summary"]["static_checks"], "fail")
        self.assertEqual(report["summary"]["capabilities"]["provider-jobs"]["state"], "blocked")

    def test_report_never_contains_secret_material_accounts_machine_identity_or_private_paths(self):
        self.host.write_backup()
        with patch.dict(os.environ, {"NEPTUNE_TEST_PROVIDER_TOKEN": "env-canary-5d1c"}):
            text = json.dumps(self.host.report())
        for canary in (CANARY, "env-canary-5d1c", COORD_NAME, WORKER_NAME, str(self.host.base), MACHINE_ID,
                       "private-other-project", "github-app.pem", "image.bin", "/home/sim-"):
            self.assertNotIn(canary, text)
        self.assertIn("neptune-coordinator.service", text)   # an operator-watched unit is kept

    def test_credential_contents_are_never_opened(self):
        paths = {str(self.host.credential(name)) for name in self.host.decl["credentials"]}
        WATCHED.update(paths)
        self.addCleanup(WATCHED.clear)
        OPENED.clear()
        with open(next(iter(paths))):
            pass
        self.assertEqual(len(OPENED), 1, "control: the audit hook must see a deliberate open")
        OPENED.clear()
        self.host.write_backup()
        report = self.host.report()
        self.assertEqual(OPENED, [])
        self.assertEqual(report["summary"]["static_checks"], "pass")

    def test_credential_files_in_an_unsafe_state_are_misconfigured(self):
        def readable_by_group(host, path):
            os.chmod(path, 0o640)

        def readable_by_all(host, path):
            os.chmod(path, 0o644)

        def empty(host, path):
            path.write_text("")

        def other_owner(host, path):
            host.probe.owners[str(path)] = (WORKER, WORKER)

        def symlink(host, path):
            target = host.base / "elsewhere"
            target.write_text("x")
            os.chmod(target, 0o600)
            path.unlink()
            path.symlink_to(target)

        def directory(host, path):
            path.unlink()
            path.mkdir()

        def parent_writable(host, path):
            os.chmod(path.parent, 0o770)

        def parent_foreign(host, path):
            host.probe.owners[str(path.parent)] = (WORKER, WORKER)

        for name, damage in (("group-readable", readable_by_group), ("world-readable", readable_by_all), ("empty", empty),
                             ("wrong owner", other_owner), ("symlink", symlink), ("directory", directory),
                             ("writable parent", parent_writable), ("foreign parent", parent_foreign)):
            with self.subTest(name):
                host = Host(self)
                damage(host, host.credential("provider-coordinator"))
                self.assertEqual(host.checks()["credential.provider-coordinator"]["status"], "misconfigured")

    def test_credentials_inside_repositories_workspaces_or_worker_home_are_misconfigured(self):
        for name, place in (("repo checkout", lambda h: h.repo / "secret"),
                            ("canonical repos", lambda h: h.root / "repos/secret"),
                            ("workspaces", lambda h: h.root / "workspaces/secret"),
                            ("worker home", lambda h: h.base / "home/worker/secret")):
            with self.subTest(name):
                host = Host(self)
                host.probe.accounts[WORKER_NAME]["home"] = str(host.base / "home/worker")
                path = place(host)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(CANARY)
                os.chmod(path, 0o600)
                host.probe.owners[str(path)] = host.probe.owners[str(path.parent)] = (COORDINATOR, COORDINATOR)
                declaration = copy.deepcopy(host.decl)
                declaration["credentials"]["provider-coordinator"]["path"] = str(path)
                check = host.checks(contract.validate(declaration))["credential.provider-coordinator"]
                self.assertEqual(check["status"], "misconfigured")
                self.assertIn("repository, workspace or worker home", check["detail"])

    def test_one_credential_file_cannot_serve_both_roles_and_each_role_needs_its_own(self):
        host = self.host
        worker_file = host.credential("github-worker")
        worker_file.unlink()
        os.link(host.credential("github-coordinator"), worker_file)
        self.assertEqual(host.checks()["credential.separation"]["status"], "misconfigured")
        worker_file.unlink()
        self.assertEqual(host.checks()["credential.separation"]["status"], "absent")
        self.assertIn("worker", host.checks()["credential.separation"]["detail"])

    def test_roles_must_be_distinct_unprivileged_and_without_container_socket_access(self):
        cases = {
            "shared uid": (lambda h: h.probe.accounts.update({WORKER_NAME: account(COORDINATOR)}),
                           "identity.separation", "misconfigured"),
            "root worker": (lambda h: h.probe.accounts.update({WORKER_NAME: account(0)}), "identity.worker", "misconfigured"),
            "docker group": (lambda h: h.probe.accounts.update({WORKER_NAME: account(WORKER, groups=("docker",))}),
                             "identity.worker-privileges", "misconfigured"),
            "sudo group": (lambda h: h.probe.accounts.update({WORKER_NAME: account(WORKER, groups=("sudo",))}),
                           "identity.worker-privileges", "misconfigured"),
            "unknown account": (lambda h: h.probe.accounts.pop(WORKER_NAME), "identity.worker", "absent"),
            "coordinator in docker group is allowed": (
                lambda h: h.probe.accounts.update({COORD_NAME: account(COORDINATOR, groups=("docker",))}),
                "identity.worker-privileges", "ok"),
        }
        for name, (damage, check_id, expected) in cases.items():
            with self.subTest(name):
                host = Host(self)
                damage(host)
                self.assertEqual(host.checks()[check_id]["status"], expected)

    def test_container_sockets_reachable_by_the_worker_are_misconfigured(self):
        def socket(mode, gid):
            return SimpleNamespace(st_mode=stat.S_IFSOCK | mode, st_uid=0, st_gid=gid, st_size=0, st_dev=1, st_ino=77)

        cases = (("owner only", 0o600, 0, "ok"), ("root group only", 0o660, 0, "ok"),
                 ("other readable", 0o666, 0, "misconfigured"), ("worker group", 0o660, WORKER, "misconfigured"))
        for name, mode, gid, expected in cases:
            with self.subTest(name):
                host = Host(self)
                host.probe.virtual["/var/run/docker.sock"] = socket(mode, gid)
                self.assertEqual(host.checks()["identity.container-sockets"]["status"], expected)

    def test_media_needs_a_dedicated_read_only_mount_when_the_declaration_requires_one(self):
        root_only = "25 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n"
        read_only_root = "25 1 8:1 / / ro,relatime - ext4 /dev/sda1 ro\n"
        # The mount point names this simulated host's root, so the covering mount is the
        # one that actually protects this host's input directory.
        for name, kind, expected in (("no read-only mount", "none", "misconfigured"),
                                     ("only the root filesystem is read-only", "root", "misconfigured"),
                                     ("read-only mount on the parent", "parent", "ok"),
                                     ("read-only superblock", "superblock", "ok"),
                                     ("mount table unreadable", "unreadable", "indeterminate")):
            with self.subTest(name):
                host = Host(self)
                if kind == "root":
                    text = root_only + read_only_root
                elif kind == "parent":
                    text = root_only + "40 25 8:1 /media %s ro,relatime - ext4 /dev/sda1 rw\n" % (host.root / "private")
                elif kind == "superblock":
                    text = root_only + "40 25 8:1 /media %s rw,relatime - ext4 /dev/sda1 ro\n" % (host.root / "private/disc")
                elif kind == "unreadable":
                    text = None
                else:
                    text = root_only
                host.probe.texts["/proc/self/mountinfo"] = text
                if text is None:
                    del host.probe.texts["/proc/self/mountinfo"]
                status = host.checks()["input.saturn-disc.protection"]["status"]
                self.assertEqual(status, expected)

    def test_permission_enforced_media_must_have_no_write_bits_or_symlinks(self):
        host = self.host
        declaration = copy.deepcopy(host.decl)
        declaration["inputs"]["saturn-disc"]["enforcement"] = "permissions"
        host.probe.texts["/proc/self/mountinfo"] = ""
        self.assertEqual(host.checks(contract.validate(declaration))["input.saturn-disc.protection"]["status"], "ok")
        os.chmod(host.root / "private/disc/image.bin", 0o600)
        check = host.checks(contract.validate(declaration))["input.saturn-disc.protection"]
        self.assertEqual(check["status"], "misconfigured")
        self.assertIn("write permission", check["detail"])
        os.chmod(host.root / "private/disc/image.bin", 0o400)
        os.chmod(host.root / "private/disc", 0o700)
        self.assertEqual(host.checks(contract.validate(declaration))["input.saturn-disc.protection"]["status"], "misconfigured")
        os.chmod(host.root / "private/disc", 0o700)
        os.symlink("/nonexistent/target", host.root / "private/disc/link")
        os.chmod(host.root / "private/disc", 0o500)
        check = host.checks(contract.validate(declaration))["input.saturn-disc.protection"]
        self.assertEqual(check["status"], "misconfigured")
        self.assertIn("symlinks", check["detail"])

    def test_workers_cannot_reach_private_inputs_state_or_modify_repositories(self):
        for name, damage, check_id in (
                ("group readable input", lambda h: (h.probe.owners.update({str(h.root / "private/captures"): (COORDINATOR, WORKER)}),
                                                    os.chmod(h.root / "private/captures", 0o750),
                                                    os.chmod(h.root / "private", 0o755)),
                 "input.captures.protection"),
                ("world readable input", lambda h: (os.chmod(h.root / "private", 0o755),
                                                    os.chmod(h.root / "private/settings", 0o755)),
                 "input.emulator-settings.protection"),
                ("worker owned input", lambda h: h.probe.owners.update({str(h.root / "private/manifests"): (WORKER, WORKER)}),
                 "input.manifests.protection"),
                ("worker readable state", lambda h: (h.probe.owners.update({str(h.root / "state"): (COORDINATOR, WORKER)}),
                                                     os.chmod(h.root / "state", 0o750)), "layout.state"),
                ("worker writable repos", lambda h: (h.probe.owners.update({str(h.root / "repos"): (COORDINATOR, WORKER)}),
                                                     os.chmod(h.root / "repos", 0o770)), "layout.repos"),
                ("world accessible workspaces", lambda h: os.chmod(h.root / "workspaces", 0o707), "layout.workspaces"),
                ("root owned workspaces", lambda h: h.probe.owners.update({str(h.root / "workspaces"): (0, 0)}),
                 "layout.workspaces"),
                ("symlinked state", lambda h: (shutil.rmtree(h.root / "state"), os.symlink(h.base, h.root / "state")),
                 "layout.state")):
            with self.subTest(name):
                host = Host(self)
                damage(host)
                self.assertEqual(host.checks()[check_id]["status"], "misconfigured", check_id)

    def test_a_private_parent_hides_a_permissive_leaf_from_the_worker(self):
        host = self.host
        host.probe.owners[str(host.root / "private/captures")] = (COORDINATOR, WORKER)
        os.chmod(host.root / "private/captures", 0o750)
        check = host.checks()["input.captures.protection"]
        self.assertEqual(check["status"], "ok")
        self.assertEqual(check["facts"]["worker_access"], "none")
        os.chmod(host.root / "private", 0o710)
        host.probe.owners[str(host.root / "private")] = (COORDINATOR, WORKER)
        self.assertEqual(host.checks()["input.captures.protection"]["status"], "misconfigured")

    def test_required_software_python_floor_and_optional_tools(self):
        host = self.host
        host.probe.programs.pop("git")
        host.probe.programs.pop("Xvfb")
        host.probe.python_version = (3, 10, 12)
        host.probe.commands[("openssl", "version")] = None
        host.probe.commands[("make", "--version")] = (1, "", "boom")
        host.probe.commands[("c++", "--version")] = (0, "\n\n", "")
        report = host.report()
        checks = {c["id"]: c for c in report["checks"]}
        self.assertEqual(checks["software.git"]["status"], "absent")
        self.assertFalse(checks["software.git"]["optional"])
        self.assertEqual(checks["software.python3"]["status"], "unsupported")
        for name in ("openssl", "make", "c++"):
            self.assertEqual(checks["software." + name]["status"], "indeterminate", name)
        self.assertEqual(checks["software.Xvfb"]["status"], "absent")
        self.assertTrue(checks["software.Xvfb"]["optional"])
        self.assertNotIn("software.Xvfb", report["summary"]["blocking"])
        for name in ("software.git", "software.python3", "software.openssl"):
            self.assertIn(name, report["summary"]["blocking"])
        self.assertEqual(report["summary"]["capabilities"]["offline-verification"]["state"], "blocked")
        self.assertEqual(report["summary"]["capabilities"]["native-runtime"]["state"], "static-checks-pass")

    def test_required_baseline_covers_what_the_verifier_declares(self):
        required = {name for name, _arguments, mandatory, _tags in readiness.SOFTWARE if mandatory}
        self.assertTrue(set(verify.BASELINE_EXECUTABLES) <= required)
        self.assertIn("python3", required)

    def test_backup_needs_an_off_host_transfer_tool(self):
        host = self.host
        for name in ("rclone", "rsync", "ssh"):
            host.probe.programs.pop(name, None)
        check = host.checks()["software.backup-transport"]
        self.assertEqual(check["status"], "absent")
        host.probe.programs["rsync"] = "/usr/bin/rsync"
        host.probe.commands[("rsync", "--version")] = (0, "rsync  version 3.4.1\n", "")
        self.assertEqual(host.checks()["software.backup-transport"]["status"], "ok")
        self.assertIn("rsync", host.report()["summary"]["installed_software"])

    def test_unsupported_platform_is_blocking(self):
        self.host.probe.system_facts["machine"] = "aarch64"
        check = self.host.checks()["host.platform"]
        self.assertEqual(check["status"], "unsupported")
        self.assertEqual(self.host.report()["summary"]["static_checks"], "fail")

    def test_probe_failures_fail_closed_without_aborting_the_report(self):
        host = self.host
        host.write_backup()
        host.probe.denied.add(str(host.root / "state"))
        report = host.report()
        checks = {c["id"]: c for c in report["checks"]}
        self.assertEqual(checks["layout.probe"]["status"], "indeterminate")
        self.assertEqual(checks["layout.probe"]["detail"], "probe failed: PermissionError")
        self.assertNotIn("state", checks["layout.probe"]["detail"])
        self.assertEqual(checks["software.git"]["status"], "ok")
        self.assertEqual(report["summary"]["static_checks"], "fail")
        self.assertIn("layout.probe", report["summary"]["blocking"])
        host.probe.denied = {str(host.root)}
        self.assertEqual({c["id"]: c for c in host.report()["checks"]}["layout.root"]["status"], "indeterminate")

    def test_root_must_be_a_real_path(self):
        host = self.host
        link = host.base / "link-to-neptune"
        link.symlink_to(host.root)
        declaration = copy.deepcopy(host.decl)
        declaration["root"] = str(link)
        self.assertEqual(host.checks(contract.validate(declaration))["layout.root"]["status"], "misconfigured")

    def test_resources_and_services_are_recorded_with_unrelated_services_redacted(self):
        report = self.host.report()
        facts = report["host"]
        self.assertEqual(facts["os"], {"id": "debian", "version_id": "13", "pretty_name": "Debian GNU/Linux 13 (trixie)"})
        self.assertEqual(facts["architecture"], "x86_64")
        self.assertEqual(facts["cpus"], {"logical": 4, "usable": 3})
        self.assertEqual(facts["memory"], {"total_bytes": 8000000 * 1024, "available_bytes": 5000000 * 1024,
                                           "swap_total_bytes": 1000000 * 1024})
        self.assertEqual(facts["host_id"], contract.host_id_from(MACHINE_ID))
        filesystem = facts["filesystems"][0]
        self.assertEqual((filesystem["total_bytes"], filesystem["free_bytes"]), (100 * 1024**3, 40 * 1024**3))
        self.assertIn("directory:state", filesystem["keys"])
        services = facts["services"]
        self.assertEqual(services["status"], "ok")
        self.assertEqual(services["running_count"], 3)
        self.assertEqual(services["watched"]["neptune-*.service"], ["neptune-coordinator.service"])
        self.assertEqual(services["watched"]["repo-factory*.service"], [])
        self.assertEqual(services["other_running_count"], 2)
        self.assertEqual(len(services["digest"]), 64)
        self.host.probe.commands = {key: value for key, value in self.host.probe.commands.items() if key[0] != "systemctl"}
        self.assertEqual(self.host.report()["host"]["services"]["status"], "unavailable")
        self.host.probe.programs.pop("systemctl")
        self.assertEqual(self.host.report()["host"]["services"]["status"], "unavailable")

    def test_parsers_tolerate_missing_and_hostile_system_files(self):
        self.assertEqual(readiness.parse_os_release(None), {"id": None, "version_id": None, "pretty_name": None})
        self.assertEqual(readiness.parse_os_release("garbage\n=x\nID=\"a b\"\n")["id"], "a b")
        self.assertEqual(readiness.parse_meminfo("MemTotal: nonsense kB\n")["total_bytes"], None)
        self.assertEqual(readiness.parse_mountinfo("short line\n- - -\n"), [])
        mounts = readiness.parse_mountinfo(r"40 25 8:1 / /srv/my\040disk ro,nosuid - ext4 /dev/x rw" + "\n")
        self.assertEqual(mounts[0]["point"], "/srv/my disk")
        self.assertIsNone(readiness.covering_mount([], "/srv"))
        self.assertEqual(readiness.covering_mount(mounts, "/srv/my disk/data")["fstype"], "ext4")
        self.assertIsNone(readiness.covering_mount(mounts, "/srv/my diskette"))

    def test_real_probe_runs_children_with_a_sanitised_environment_and_bounded_output(self):
        probe = readiness.Probe()
        with patch.dict(os.environ, {"NEPTUNE_TEST_PROVIDER_TOKEN": "env-canary-5d1c", "PYTHONPATH": "/tmp/planted"}):
            code, out, _ = probe.run([sys.executable, "-I", "-c", "import os; print(sorted(os.environ))"])
        self.assertEqual(code, 0)
        self.assertNotIn("env-canary", out)
        self.assertNotIn("PYTHONPATH", out)
        self.assertIsNone(probe.run(["/nonexistent/tool"]))
        self.assertIsNone(probe.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2))
        code, out, _ = probe.run([sys.executable, "-c", "print('x' * 200000)"])
        self.assertEqual(len(out), 65536)

    def test_real_probe_reads_generic_host_facts_without_touching_declared_paths(self):
        probe = readiness.Probe()
        with tempfile.TemporaryDirectory() as directory:
            total, free = probe.disk_usage(directory)
            self.assertTrue(0 < free <= total)
            self.assertIsNone(probe.lstat(os.path.join(directory, "missing")))
            self.assertIsNone(probe.read_text(os.path.join(directory, "missing")))
            self.assertEqual(probe.listdir(directory), [])
        logical, usable = probe.cpus()
        self.assertTrue(1 <= usable <= logical)
        self.assertEqual(probe.system()["machine"], os.uname().machine)
        self.assertIsNone(probe.account("no-such-account-4f7e91"))
        self.assertIsNone(probe.which("definitely-not-installed-4f7e91"))


class BackupChecks(unittest.TestCase):
    def setUp(self):
        self.host = Host(self)

    def status(self, name):
        return self.host.checks()[name]["status"]

    def test_unconfigured_backup_is_absent_not_ok(self):
        declaration = copy.deepcopy(self.host.decl)
        declaration["backup"].update(key=None, max_age_seconds=None, sources=[])
        checks = self.host.checks(contract.validate(declaration))
        self.assertEqual(checks["backup.configuration"]["status"], "absent")
        self.assertEqual(checks["backup.configuration"]["detail"], "not configured: key, max_age_seconds, sources")
        self.assertEqual(checks["backup.archive"]["status"], "absent")

    def test_current_archive_and_drill_are_ok_and_off_host_origin_stays_attested(self):
        self.host.write_backup()
        checks = self.host.checks()
        self.assertEqual(checks["backup.archive"]["status"], "ok")
        self.assertEqual(checks["backup.restore-drill"]["status"], "ok")
        offhost = checks["backup.offhost"]
        self.assertEqual(offhost["status"], "present-unverified")
        self.assertIn("operator-attested", offhost["detail"])
        self.assertTrue(offhost["facts"]["independent_host"])

    def test_restore_on_the_source_host_is_reported_as_not_independent(self):
        self.host.write_backup(independent=False)
        offhost = self.host.checks()["backup.offhost"]
        self.assertEqual(offhost["status"], "present-unverified")
        self.assertIn("independent-host recovery is unproven", offhost["detail"])
        self.host.write_backup(independent=None, restore_host_id=None)
        self.assertIn("independent-host recovery is unproven", self.host.checks()["backup.offhost"]["detail"])

    def test_a_local_copy_does_not_demonstrate_an_off_host_restore(self):
        self.host.write_backup(origin="local")
        self.assertEqual(self.status("backup.offhost"), "misconfigured")
        self.assertEqual(self.status("backup.restore-drill"), "ok")

    def test_stale_archive_and_stale_drill_are_misconfigured(self):
        self.host.write_backup(age=8 * 86400, drill_age=60)
        self.assertEqual(self.status("backup.archive"), "misconfigured")
        self.host.write_backup(age=60, drill_age=8 * 86400)
        self.assertEqual(self.status("backup.restore-drill"), "misconfigured")

    def test_future_dated_records_are_rejected(self):
        self.host.write_backup(age=-3600, drill_age=-3600)
        self.assertIn("future", self.host.checks()["backup.archive"]["detail"])
        self.assertIn("future", self.host.checks()["backup.restore-drill"]["detail"])

    def test_archive_file_must_exist_match_its_record_and_carry_the_encrypted_header(self):
        archive, _sidecar, _drill = self.host.write_backup()
        archive.write_bytes(b"NEPTUNE-NBK1\n" + b"\x00" * 10)
        self.assertIn("size differs", self.host.checks()["backup.archive"]["detail"])
        archive.write_bytes((b"ustar plain tar" + bytes(77))[:77])
        self.assertIn("header", self.host.checks()["backup.archive"]["detail"])
        archive.unlink()
        self.assertIn("missing", self.host.checks()["backup.archive"]["detail"])
        self.assertEqual(self.status("backup.archive"), "misconfigured")

    def test_drill_must_match_a_recorded_archive_and_verify_everything(self):
        for name, change in (("different archive", {"archive_sha256": "9" * 64}),
                             ("different manifest", {"manifest_sha256": "9" * 64}),
                             ("files skipped", {"files_verified": 4}),
                             ("database failed", {"sqlite_ok": 0})):
            with self.subTest(name):
                self.host.write_backup(**change)
                self.assertEqual(self.status("backup.restore-drill"), "misconfigured")

    def test_malformed_receipts_are_rejected_not_trusted(self):
        archive, sidecar, drill = self.host.write_backup()
        cases = {"extra field": lambda v: v.update(surprise=1), "missing field": lambda v: v.pop("files_verified"),
                 "string count": lambda v: v.update(files_verified="5"), "bool count": lambda v: v.update(files_verified=True),
                 "unattested": lambda v: v.update(origin_attested=False), "bad schema": lambda v: v.update(schema="x")}
        original = json.loads(drill.read_text())
        for name, change in cases.items():
            with self.subTest(name):
                value = copy.deepcopy(original)
                change(value)
                drill.write_text(json.dumps(value))
                self.assertEqual(self.status("backup.restore-drill"), "misconfigured")
        drill.write_text('{"schema": "a", "schema": "b"}')
        self.assertEqual(self.status("backup.restore-drill"), "misconfigured")
        drill.unlink()
        self.assertEqual(self.status("backup.restore-drill"), "absent")
        drill.write_text(json.dumps(original))
        sidecar.write_text("{")
        self.assertEqual(self.status("backup.archive"), "absent")

    def test_freshness_cannot_be_judged_without_a_declared_maximum_age(self):
        self.host.write_backup()
        declaration = copy.deepcopy(self.host.decl)
        declaration["backup"]["max_age_seconds"] = None
        checks = self.host.checks(contract.validate(declaration))
        self.assertEqual(checks["backup.archive"]["status"], "indeterminate")
        self.assertEqual(checks["backup.restore-drill"]["status"], "indeterminate")
        self.assertEqual(checks["backup.configuration"]["status"], "absent")


class CommandLine(unittest.TestCase):
    def run_main(self, *arguments, host=None):
        out, err = io.StringIO(), io.StringIO()
        probe = host.probe if host else FakeProbe("/nonexistent-base")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                patch.object(readiness, "Probe", lambda: probe):
            code = readiness.main(list(arguments))
        return code, out.getvalue(), err.getvalue()

    def test_template_prints_a_valid_unconfigured_declaration(self):
        code, out, err = self.run_main("template")
        self.assertEqual((code, err), (0, ""))
        contract.validate(json.loads(out))

    def test_report_reads_the_declaration_and_writes_only_new_evidence(self):
        host = Host(self)
        host.write_backup()
        path = host.base / "declaration.json"
        path.write_text(json.dumps(host.decl))
        code, out, err = self.run_main("report", "--declaration", str(path), "--strict", host=host)
        self.assertEqual((code, err), (0, ""))
        report = json.loads(out)
        self.assertEqual(report["summary"]["static_checks"], "pass")
        self.assertEqual(report["identity"]["declaration_sha256"], contract.load_declaration(path)[1])
        output = host.base / "report.json"
        code, out, err = self.run_main("report", "--declaration", str(path), "--output", str(output), host=host)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read_text())["schema"], readiness.SCHEMA)
        self.assertEqual(json.loads(out)["static_checks"], "pass")
        self.assertEqual(stat.S_IMODE(output.stat().st_mode) & 0o007, 0)
        before = output.read_bytes()
        code, out, err = self.run_main("report", "--declaration", str(path), "--output", str(output), host=host)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("FAIL: Refusing to overwrite existing evidence", err)
        self.assertEqual(output.read_bytes(), before)

    def test_strict_exits_nonzero_for_blockers_and_failures_print_no_report(self):
        host = Host(self)
        host.credential("provider-coordinator").unlink()
        path = host.base / "declaration.json"
        path.write_text(json.dumps(host.decl))
        code, out, _ = self.run_main("report", "--declaration", str(path), host=host)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"]["static_checks"], "fail")
        code, out, _ = self.run_main("report", "--declaration", str(path), "--strict", host=host)
        self.assertEqual(code, 1)
        broken = host.base / "broken.json"
        broken.write_text('{"schema": "x"}')
        code, out, err = self.run_main("report", "--declaration", str(broken), host=host)
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("FAIL: "))
        code, out, err = self.run_main("report", "--declaration", str(host.base / "absent.json"), host=host)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("missing", err)


if __name__ == "__main__":
    unittest.main()
