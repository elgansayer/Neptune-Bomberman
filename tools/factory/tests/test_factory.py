from copy import deepcopy
import json
import multiprocessing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from readiness import ContractError, evaluate
from store import JobStore


def snapshot(issue=71, feature="FACTORY-001", path="tools/factory"):
    return {"schema": "neptune.factory-intake.v1", "captured_at": 1000, "base_sha": "a" * 40,
            "task": {"repository": "example/game", "issue": issue, "feature_id": feature,
                     "revision": "b" * 64, "kind": "implementation", "state": "open",
                     "acceptance": ["Reject stale intake"], "evidence": ["Run failure cases"],
                     "prerequisites": [], "capabilities": ["python"],
                     "scope": {"goal": "Validate readiness", "paths": [path], "max_files": 10}},
            "available_capabilities": ["python"], "prerequisite_evidence": {}, "active_work": []}


def compete(path, job, owner, start, output):
    store = JobStore(path, lambda: 1000)
    try:
        if not start.wait(10):
            raise RuntimeError("start barrier timed out")
        try:
            output.put(("won", store.claim(job, owner)))
        except ContractError as error:
            output.put(("lost", str(error)))
    finally:
        store.close()


def interrupted_write(path, job, ready):
    store = JobStore(path, lambda: 1000)
    store.db.execute("BEGIN IMMEDIATE")
    store.db.execute("UPDATE jobs SET checkpoint='uncommitted' WHERE id=?", (job,))
    ready.set()
    # Parent terminates the process while SQLite owns an unfinished transaction.
    multiprocessing.Event().wait(20)


class Intake(unittest.TestCase):
    def test_complete_snapshot_is_ready(self):
        result = evaluate(snapshot(), 1000)
        self.assertTrue(result["ready"])
        self.assertEqual(len(result["task_digest"]), 64)

    def test_missing_contract_fields_are_not_ready(self):
        for field in snapshot()["task"]:
            value = snapshot()
            del value["task"][field]
            with self.subTest(field=field):
                self.assertFalse(evaluate(value, 1000)["ready"])

    def test_epic_empty_acceptance_and_unbounded_scope_rejected(self):
        changes = [("kind", "epic"), ("kind", "roadmap"), ("state", "closed"),
                   ("acceptance", []), ("evidence", [""]), ("revision", "current"),
                   ("feature_id", "TODO"), ("issue", True)]
        for key, value in changes:
            data = snapshot()
            data["task"][key] = value
            with self.subTest(key=key, value=value):
                self.assertFalse(evaluate(data, 1000)["ready"])
        for value in (0, 21, True, "5"):
            data = snapshot()
            data["task"]["scope"]["max_files"] = value
            self.assertFalse(evaluate(data, 1000)["ready"])

    def test_literal_safe_paths_required(self):
        for path in (".", "/etc", "../game", "ai/../game", "ai//tasks", "ai/*", "ai/", "C:\\game"):
            with self.subTest(path=path):
                self.assertFalse(evaluate(snapshot(path=path), 1000)["ready"])

    def test_stale_future_missing_capability_fail(self):
        self.assertFalse(evaluate(snapshot(), 1901)["ready"])
        self.assertFalse(evaluate(snapshot(), 999)["ready"])
        value = snapshot()
        value["available_capabilities"] = []
        self.assertIn("missing capabilities: python", evaluate(value, 1000)["reasons"])

    def test_closed_prerequisite_is_not_verified_evidence(self):
        data = snapshot()
        data["task"]["prerequisites"] = ["SIM-001"]
        for proof in ({}, {"state": "closed"}, {"status": "verified"}):
            data["prerequisite_evidence"]["SIM-001"] = proof
            self.assertFalse(evaluate(data, 1000)["ready"])
        data["prerequisite_evidence"]["SIM-001"] = {"status": "verified", "head_sha": "c" * 40, "base_sha": "d" * 40, "report_sha256": "e" * 64, "evidence_ref": "private:evidence/accepted"}
        self.assertTrue(evaluate(data, 1000)["ready"])

    def test_pr_overlap_by_feature_issue_or_path(self):
        for issue, feature, path in ((71, "OTHER-001", "elsewhere"), (99, "FACTORY-001", "elsewhere"), (99, "OTHER-001", "tools/factory/store.py"), (99, "OTHER-001", "tools")):
            data = snapshot()
            data["active_work"] = [{"repository": "example/game", "kind": "pr", "state": "open", "issue": issue, "feature_id": feature, "paths": [path]}]
            self.assertFalse(evaluate(data, 1000)["ready"])

    def test_path_prefix_and_other_repository_do_not_collide(self):
        data = snapshot()
        work = {"repository": "example/game", "kind": "pr", "state": "open", "issue": 99, "feature_id": "OTHER-001", "paths": ["tools/factory_extra"]}
        data["active_work"] = [work]
        self.assertTrue(evaluate(data, 1000)["ready"])
        work.update(repository="another/game", paths=["tools/factory"])
        self.assertTrue(evaluate(data, 1000)["ready"])

    def test_expired_external_claim_needs_reconciliation(self):
        data = snapshot()
        data["active_work"] = [{"repository": "example/game", "kind": "lease", "issue": 71, "feature_id": "FACTORY-001", "paths": ["tools/factory"], "expires_at": 999}]
        self.assertFalse(evaluate(data, 1000)["ready"])

    def test_unknown_or_missing_active_work_fails_closed(self):
        for record in (None, [{}], [{"kind": "magic"}]):
            data = snapshot()
            data["active_work"] = record
            self.assertFalse(evaluate(data, 1000)["ready"])

    def test_cli_bad_input_and_stale_snapshot_exit_nonzero(self):
        cli = Path(__file__).resolve().parents[1] / "cli.py"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            for content in ("{", json.dumps(snapshot())):
                path.write_text(content)
                result = subprocess.run([sys.executable, str(cli), "readiness", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)


class Leases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.sqlite"
        self.now = 1000
        self.store = JobStore(self.path, lambda: self.now)
        self.addCleanup(lambda: self.store.close())
        self.job = self.store.enqueue(snapshot())

    def receipt(self, ttl=10):
        return self.store.claim(self.job, "worker-a", ttl)

    def test_duplicate_delivery_and_changed_intake(self):
        self.assertEqual(self.job, self.store.enqueue(snapshot()))
        changed = snapshot()
        changed["task"]["revision"] = "c" * 64
        with self.assertRaisesRegex(ContractError, "changed task"):
            self.store.enqueue(changed)
        with self.assertRaises(ContractError):
            self.store.enqueue(snapshot(feature="FACTORY-002"))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_owned_refresh_is_rejected(self):
        self.receipt()
        with self.assertRaisesRegex(ContractError, "owned"):
            self.store.enqueue(snapshot())

    def test_only_one_real_process_claims_same_job(self):
        ctx = multiprocessing.get_context("spawn")
        start, output = ctx.Event(), ctx.Queue()
        workers = [ctx.Process(target=compete, args=(str(self.path), self.job, str(i), start, output)) for i in range(2)]
        for worker in workers:
            worker.start()
        start.set()
        answers = [output.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(10)
            if worker.is_alive():
                worker.terminate()
                worker.join()
                self.fail("claim process hung")
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(sorted(answer[0] for answer in answers), ["lost", "won"])

    def test_scope_overlap_across_distinct_jobs(self):
        other = self.store.enqueue(snapshot(72, "FACTORY-002", "tools/factory/store.py"))
        self.receipt()
        with self.assertRaisesRegex(ContractError, "reserved"):
            self.store.claim(other, "worker-b")

    def test_independent_scope_can_be_claimed(self):
        other = self.store.enqueue(snapshot(27, "REF-001", "tools/saturn_lab"))
        self.receipt()
        self.assertEqual(self.store.claim(other, "worker-b")["owner"], "worker-b")

    def test_repository_case_cannot_bypass_reservation(self):
        data = snapshot(72, "FACTORY-002", "tools/factory/other.py")
        data["task"]["repository"] = "EXAMPLE/Game"
        other = self.store.enqueue(data)
        self.receipt()
        with self.assertRaisesRegex(ContractError, "reserved"):
            self.store.claim(other, "worker-b")

    def test_heartbeat_extends_current_lease(self):
        receipt = self.receipt()
        self.now = 1009
        self.store.heartbeat(receipt, 20)
        self.now = 1011
        with self.assertRaises(ContractError):
            self.store.claim(self.job, "worker-b")
        self.assertEqual(self.store.get(self.job)["expires"], 1029)

    def test_expiry_fences_old_worker_and_preserves_checkpoint_on_restart(self):
        old = self.receipt()
        checkpoint = {"base_sha": "a" * 40, "head_sha": "b" * 40, "next_step": "resume tests", "evidence_ref": "private:logs/1"}
        self.store.checkpoint(old, checkpoint)
        self.store.close()
        self.now = 1010
        self.store = JobStore(self.path, lambda: self.now)
        new = self.store.claim(self.job, "worker-b")
        self.assertGreater(new["epoch"], old["epoch"])
        self.assertEqual(new["checkpoint"], checkpoint)
        for operation in (lambda: self.store.heartbeat(old), lambda: self.store.checkpoint(old, checkpoint), lambda: self.store.release(old, "ready", "stale"), lambda: self.store.begin_publication(old, {"head_sha": "b" * 40, "base_sha": "a" * 40, "branch": "old"})):
            with self.assertRaises(ContractError):
                operation()

    def test_foreign_owner_or_token_cannot_mutate(self):
        receipt = self.receipt()
        for key, value in (("owner", "intruder"), ("token", "bad"), ("epoch", 999), ("task_digest", "bad")):
            foreign = {**receipt, key: value}
            with self.assertRaises(ContractError):
                self.store.heartbeat(foreign)

    def test_cancel_fences_worker_and_requires_reconciliation(self):
        receipt = self.receipt()
        self.store.cancel(self.job, "operator stop")
        with self.assertRaises(ContractError):
            self.store.heartbeat(receipt)
        with self.assertRaises(ContractError):
            self.store.claim(self.job, "worker-b")

    def test_crash_during_publication_blocks_duplicate_publication(self):
        receipt = self.receipt()
        intent = {"head_sha": "b" * 40, "base_sha": "a" * 40, "branch": "worker/change"}
        self.store.begin_publication(receipt, intent)
        self.store.begin_publication(receipt, intent)
        self.now = 1011
        self.store.recover()
        row = self.store.get(self.job)
        self.assertEqual(row["state"], "blocked")
        self.assertIn("unknown", row["reason"])
        with self.assertRaises(ContractError):
            self.store.claim(self.job, "replacement")
        other = self.store.enqueue(snapshot(72, "FACTORY-002", "tools/factory/other.py"))
        with self.assertRaises(ContractError):
            self.store.claim(other, "replacement")
        self.store.reconcile(self.job, row["epoch"], "clear", "checked:no old process, branch or PR")
        self.assertEqual(self.store.claim(self.job, "replacement")["owner"], "replacement")

    def test_cannot_requeue_or_change_publication_intent(self):
        receipt = self.receipt()
        intent = {"head_sha": "b" * 40, "base_sha": "a" * 40, "branch": "worker/change"}
        self.store.begin_publication(receipt, intent)
        with self.assertRaises(ContractError):
            self.store.release(receipt, "ready", "retry")
        with self.assertRaises(ContractError):
            self.store.begin_publication(receipt, {**intent, "head_sha": "c" * 40})

    def test_killed_process_rolls_back_partial_checkpoint(self):
        ctx = multiprocessing.get_context("spawn")
        ready = ctx.Event()
        worker = ctx.Process(target=interrupted_write, args=(str(self.path), self.job, ready))
        worker.start()
        try:
            self.assertTrue(ready.wait(10))
        finally:
            worker.terminate()
            worker.join(10)
        self.assertIsNone(self.store.get(self.job)["checkpoint"])
        self.assertEqual(self.receipt()["owner"], "worker-a")

    def test_stale_snapshot_requires_refresh_before_reclaim(self):
        self.receipt()
        self.now = 2000
        self.store.recover()
        with self.assertRaisesRegex(ContractError, "stale"):
            self.receipt()
        refreshed = snapshot()
        refreshed["captured_at"] = self.now
        self.store.enqueue(refreshed)
        self.receipt()

    def test_clock_rollback_fails_closed(self):
        receipt = self.receipt()
        self.now = 999
        with self.assertRaisesRegex(ContractError, "backwards"):
            self.store.heartbeat(receipt)

    def test_audit_survives_restart_and_submission_is_not_merge(self):
        receipt = self.receipt()
        self.store.begin_publication(receipt, {"head_sha": "b" * 40, "base_sha": "a" * 40, "branch": "worker/change"})
        self.store.release(receipt, "submitted", "PR created")
        self.store.close()
        self.store = JobStore(self.path, lambda: self.now)
        self.assertEqual(self.store.get(self.job)["state"], "submitted")
        self.assertEqual([row[0] for row in self.store.db.execute("SELECT event FROM events ORDER BY sequence")], ["enqueued", "claimed", "publication_started", "released"])
        with self.assertRaises(ContractError):
            self.store.reconcile(self.job, 0, "accepted", "stale reconciliation")


BINDING = {"release": "saturn-jp-1.003", "module_sha256": "f" * 64, "cpu": "master-sh2",
           "address_space": "high-work-ram", "load_lifetime": "0KRNL.BIN resident after boot"}


def result(store, job, **changes):
    checkpoint = json.loads(store.get(job)["checkpoint"])
    value = {"task_digest": store.get(job)["task_digest"], "base_sha": checkpoint["base_sha"], "head_sha": checkpoint["head_sha"],
             "report_sha256": "9" * 64, "evidence_ref": "private:evidence/experiment-001.json", "status": "verified",
             "binding": dict(BINDING), "verified": ["original-bytes"], "hypotheses": ["callsite is the scheduler resume"]}
    value.update(changes)
    return value


class Handoff(unittest.TestCase):
    """A dependent worker requests one bounded experiment and resumes exactly once."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.sqlite"
        self.now = 1000
        self.store = JobStore(self.path, lambda: self.now)
        self.addCleanup(lambda: self.store.close())
        self.producer = self.store.enqueue(snapshot(660, "CODE-001", "tools/saturn_lab"))
        self.dependent = self.store.enqueue(snapshot(779, "FACTORY-020", "tools/factory"))

    def spec(self, **changes):
        return {"producer": self.producer, "question": "Which caller reaches the resume path?", "binding": dict(BINDING), "verified": ["original-bytes"], **changes}

    def checkpointed_producer(self, head="b"):
        receipt = self.store.claim(self.producer, "codex", 60)
        self.store.checkpoint(receipt, {"base_sha": "a" * 40, "head_sha": head * 40, "next_step": "run probe"})
        return receipt

    def waiting(self):
        receipt = self.store.claim(self.dependent, "claude", 60)
        self.store.checkpoint(receipt, {"base_sha": "a" * 40, "head_sha": "c" * 40, "next_step": "use the caller result"})
        request = self.store.request(receipt, [self.spec()])["requests"][0]
        return receipt, request

    def events(self, job, name):
        return self.store.db.execute("SELECT count(*) FROM events WHERE job=? AND event=?", (job, name)).fetchone()[0]

    def test_status_shows_owner_scope_checkpoint_and_unknown_liveness(self):
        receipt = self.store.claim(self.dependent, "claude", 60)
        self.store.checkpoint(receipt, {"base_sha": "a" * 40, "head_sha": "c" * 40, "next_step": "audit"})
        jobs = {j["job"]: j for j in self.store.status()["jobs"]}
        mine = jobs[self.dependent]
        self.assertEqual((mine["owner"], mine["state"], mine["lease"]["recorded"]), ("claude", "running", True))
        self.assertEqual(mine["scope"]["paths"], ["tools/factory"])
        self.assertEqual(mine["checkpoint"], {"present": True, "head_sha": "c" * 40, "next_step": "audit"})
        self.assertTrue(mine["process_liveness"].startswith("unknown"))
        self.assertNotIn(receipt["token"], json.dumps(self.store.status()))
        self.now = 1061
        self.assertTrue({j["job"]: j for j in self.store.status()["jobs"]}[self.dependent]["lease"]["expired"])
        self.now = 2000
        self.assertIn("snapshot stale or from the future", {j["job"]: j for j in self.store.status()["jobs"]}[self.producer]["admission"])

    def test_cli_status_is_read_only_and_tokenless(self):
        receipt = self.store.claim(self.dependent, "claude", 60)
        cli = Path(__file__).resolve().parents[1] / "cli.py"
        before = self.store.db.execute("SELECT count(*) FROM events").fetchone()[0]
        output = subprocess.run([sys.executable, str(cli), "status", "--database", str(self.path)], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(output)["schema"], "neptune.factory-status.v1")
        self.assertNotIn(receipt["token"], output)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events").fetchone()[0], before)

    def test_running_cap_queues_independent_scope(self):
        self.store.close()
        self.store = JobStore(self.path, lambda: self.now, max_running=1)
        self.store.claim(self.producer, "codex")
        with self.assertRaisesRegex(ContractError, "running cap reached: 1 of 1"):
            self.store.claim(self.dependent, "claude")
        self.assertIn("running cap reached: 1 of 1", {j["job"]: j for j in self.store.status()["jobs"]}[self.dependent]["admission"])

    def test_request_waits_then_matching_result_unblocks_once(self):
        old, request = self.waiting()
        self.assertEqual(self.store.get(self.dependent)["state"], "waiting")
        with self.assertRaisesRegex(ContractError, "not ready: awaiting experiments"):
            self.store.claim(self.dependent, "other")
        with self.assertRaises(ContractError):
            self.store.heartbeat(old)
        producer = self.checkpointed_producer()
        self.assertEqual([r["request"] for r in producer["requests"]], [request])
        value = result(self.store, self.producer)
        self.assertEqual(self.store.deliver(producer, request, value), {"request": request, "satisfied": True, "duplicate": False})
        self.assertEqual(self.store.deliver(producer, request, value)["duplicate"], True)
        self.assertEqual(self.events(self.dependent, "unblocked"), 1)
        resumed = self.store.claim(self.dependent, "claude-resumed")
        self.assertEqual(resumed["checkpoint"]["next_step"], "use the caller result")
        self.assertEqual(resumed["results"][0]["result"]["report_sha256"], "9" * 64)
        self.assertEqual(resumed["results"][0]["result"]["hypotheses"], ["callsite is the scheduler resume"])
        with self.assertRaisesRegex(ContractError, "different result"):
            self.store.deliver(producer, request, {**value, "report_sha256": "8" * 64})

    def test_request_is_listed_to_producer_at_claim(self):
        _, request = self.waiting()
        self.assertEqual([r["request"] for r in self.store.claim(self.producer, "codex")["requests"]], [request])

    def test_mismatched_stale_or_missing_results_do_not_satisfy(self):
        _, request = self.waiting()
        producer = self.checkpointed_producer()
        cases = [({"task_digest": "0" * 64}, "different producer task"),
                 ({"binding": {**BINDING, "module_sha256": "e" * 64}}, "binding"),
                 ({"binding": {**BINDING, "load_lifetime": "overlay"}}, "binding"),
                 ({"head_sha": "d" * 40}, "checkpoint"),
                 ({"report_sha256": ""}, "report hash"),
                 ({"evidence_ref": ""}, "evidence"),
                 ({"status": "passed"}, "status")]
        for change, message in cases:
            with self.subTest(change=change), self.assertRaisesRegex(ContractError, message):
                self.store.deliver(producer, request, result(self.store, self.producer, **change))
        with self.assertRaisesRegex(ContractError, "fields"):
            self.store.deliver(producer, request, {k: v for k, v in result(self.store, self.producer).items() if k != "hypotheses"})
        for change in ({"status": "failed"}, {"status": "truncated"}, {"verified": []}):
            self.assertFalse(self.store.deliver(producer, request, result(self.store, self.producer, **change))["satisfied"])
        self.assertEqual(self.store.get(self.dependent)["state"], "waiting")
        self.assertEqual(self.events(self.producer, "result_rejected"), 3)
        with self.assertRaisesRegex(ContractError, "producer"):
            self.store.deliver(producer, "unknown", result(self.store, self.producer))

    def test_hypothesis_without_original_byte_verification_keeps_waiting(self):
        _, request = self.waiting()
        producer = self.checkpointed_producer()
        reply = self.store.deliver(producer, request, result(self.store, self.producer, verified=["natural-runtime"]))
        self.assertEqual(reply["reason"], "result verified; missing verification: original-bytes")
        self.assertEqual(self.store.get(self.dependent)["state"], "waiting")

    def test_stale_or_foreign_producer_cannot_deliver(self):
        _, request = self.waiting()
        old = self.checkpointed_producer()
        value = result(self.store, self.producer)
        with self.assertRaises(ContractError):
            self.store.deliver({**old, "token": "forged"}, request, value)
        self.now = 1061
        replacement = self.store.claim(self.producer, "codex-restarted")
        with self.assertRaisesRegex(ContractError, "stale|expired"):
            self.store.deliver(old, request, value)
        intruder = self.store.enqueue(snapshot(99, "OTHER-001", "docs"))
        foreign = self.store.claim(intruder, "intruder")
        self.store.checkpoint(foreign, {"base_sha": "a" * 40, "head_sha": "b" * 40, "next_step": "x"})
        with self.assertRaisesRegex(ContractError, "unknown request for this producer"):
            self.store.deliver(foreign, request, result(self.store, intruder))
        self.assertTrue(self.store.deliver(replacement, request, value)["satisfied"])

    def test_changed_producer_task_cannot_answer_old_request(self):
        _, request = self.waiting()
        self.store.db.execute("UPDATE jobs SET task_digest=? WHERE id=?", ("1" * 64, self.producer))
        producer = self.checkpointed_producer()
        with self.assertRaisesRegex(ContractError, "different producer task"):
            self.store.deliver(producer, request, result(self.store, self.producer))

    def test_request_validation(self):
        receipt = self.store.claim(self.dependent, "claude", 60)
        for specs in ([], [self.spec()] * 9, [self.spec(question="")], [self.spec(binding={})], [self.spec(verified=[])],
                      [self.spec(verified=["vibes"])], [self.spec(producer=self.dependent)], [self.spec(producer="example/game:NONE-001")],
                      [{**self.spec(), "extra": 1}]):
            with self.subTest(specs=specs), self.assertRaises(ContractError):
                self.store.request(receipt, specs)
        self.assertEqual(self.store.get(self.dependent)["state"], "running")

    def test_restart_preserves_result_and_never_redispatches(self):
        _, request = self.waiting()
        producer = self.checkpointed_producer()
        self.store.deliver(producer, request, result(self.store, self.producer))
        self.store.release(producer, "ready", "probe done")
        self.store.close()
        self.store = JobStore(self.path, lambda: self.now)
        self.assertEqual(self.store.claim(self.producer, "codex-restarted")["requests"], [])
        resumed = self.store.claim(self.dependent, "claude-restarted")
        repeated = self.store.request(resumed, [self.spec()])
        self.assertEqual((repeated["waiting"], repeated["results"][0]["request"]), ([], request))
        self.assertEqual(self.store.get(self.dependent)["state"], "running")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM requests").fetchone()[0], 1)
        self.assertEqual(self.events(self.dependent, "unblocked"), 1)

    def test_dependent_waits_for_every_requested_experiment(self):
        receipt = self.store.claim(self.dependent, "claude", 60)
        first, second = self.store.request(receipt, [self.spec(), self.spec(question="Which table does it index?")])["requests"]
        producer = self.checkpointed_producer()
        self.store.deliver(producer, first, result(self.store, self.producer))
        self.assertEqual(self.store.get(self.dependent)["state"], "waiting")
        self.assertEqual({j["job"]: j for j in self.store.status()["jobs"]}[self.dependent]["waiting_on"], [second])
        self.store.deliver(producer, second, result(self.store, self.producer))
        self.assertEqual(self.store.get(self.dependent)["state"], "ready")

    def test_cancelled_dependent_request_is_not_dispatched(self):
        self.waiting()
        self.store.cancel(self.dependent, "superseded")
        self.assertEqual(self.store.claim(self.producer, "codex")["requests"], [])

    def test_cli_drives_handoff_with_private_receipts(self):
        cli = Path(__file__).resolve().parents[1] / "cli.py"
        self.store.close()
        refreshed = []
        for issue, feature, path in ((660, "CODE-001", "tools/saturn_lab"), (779, "FACTORY-020", "tools/factory")):
            data = snapshot(issue, feature, path)
            data["captured_at"] = __import__("time").time()
            refreshed.append(data)
        self.store = JobStore(self.path)
        for data in refreshed:
            self.store.enqueue(data)
        self.store.close()
        directory = Path(self.temp.name)

        def run(*arguments, payload=None, code=0):
            extra = []
            if payload is not None:
                (directory / "payload.json").write_text(json.dumps(payload))
                extra = [str(directory / "payload.json")]
            done = subprocess.run([sys.executable, str(cli), *arguments, "--database", str(self.path), *extra], capture_output=True, text=True)
            self.assertEqual(done.returncode, code, done.stderr)
            return json.loads(done.stdout) if code == 0 else done.stderr

        dependent, producer = directory / "dependent.receipt", directory / "producer.receipt"
        claimed = run("claim", "--owner", "claude", "--receipt", str(dependent), self.dependent)
        self.assertNotIn("token", claimed)
        self.assertEqual(dependent.stat().st_mode & 0o777, 0o600)
        self.assertIn("exists", run("claim", "--owner", "claude", "--receipt", str(dependent), self.producer, code=1))
        self.assertIn("not ready", run("claim", "--owner", "x", "--receipt", str(directory / "lost.receipt"), self.dependent, code=1))
        self.assertFalse((directory / "lost.receipt").exists())
        run("checkpoint", "--receipt", str(dependent), payload={"base_sha": "a" * 40, "head_sha": "c" * 40, "next_step": "use result"})
        request = run("request", "--receipt", str(dependent), payload=[self.spec()])["requests"][0]
        self.assertFalse(dependent.exists())
        self.assertEqual([r["request"] for r in run("claim", "--owner", "codex", "--receipt", str(producer), self.producer)["requests"]], [request])
        run("checkpoint", "--receipt", str(producer), payload={"base_sha": "a" * 40, "head_sha": "b" * 40, "next_step": "deliver"})
        self.store = JobStore(self.path)
        value = result(self.store, self.producer)
        self.store.close()
        self.assertIn("binding", run("deliver", "--receipt", str(producer), "--request", request, payload={**value, "binding": {**BINDING, "cpu": "slave-sh2"}}, code=1))
        self.assertTrue(run("deliver", "--receipt", str(producer), "--request", request, payload=value)["satisfied"])
        run("release", "--receipt", str(producer), "--state", "ready", "--reason", "probe done")
        self.assertFalse(producer.exists())
        resumed = run("claim", "--owner", "claude-resumed", "--receipt", str(dependent), self.dependent)
        self.assertEqual(resumed["results"][0]["result"]["report_sha256"], "9" * 64)
        self.store = JobStore(self.path)

    def test_duplicate_request_from_two_dependents_is_independent(self):
        _, first = self.waiting()
        other = self.store.enqueue(snapshot(780, "FACTORY-021", "docs/factory"))
        receipt = self.store.claim(other, "gemini")
        second = self.store.request(receipt, [self.spec()])["requests"][0]
        self.assertNotEqual(first, second)
        producer = self.checkpointed_producer()
        self.store.deliver(producer, first, result(self.store, self.producer))
        self.assertEqual((self.store.get(self.dependent)["state"], self.store.get(other)["state"]), ("ready", "waiting"))


class ProviderAttempts(unittest.TestCase):
    """Durable attempt/spend records and bounded provider failure recovery."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.sqlite"
        self.now = 1000
        self.store = JobStore(self.path, lambda: self.now, max_attempts=2, backoff=30, max_backoff=100, spend_limit=10)
        self.addCleanup(lambda: self.store.close())
        self.job = self.store.enqueue(snapshot())

    def reopen(self):
        self.store.close()
        self.store = JobStore(self.path, lambda: self.now, max_attempts=2, backoff=30, max_backoff=100, spend_limit=10)

    def provider_failure(self, receipt, outcome="timeout", provider="codex", model="gpt-5.1", **changes):
        return self.store.record_attempt(receipt, outcome, provider, model, **changes)

    def test_success_and_spend_survive_restart(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        answer = self.store.record_attempt(receipt, "succeeded", "codex", "gpt-5.1", spend=1.5)
        self.assertEqual((answer["attempt"], answer["state"], answer["failures"], answer["spend"]), (1, "running", 0, 1.5))
        self.reopen()
        row = self.store.get(self.job)
        self.assertEqual((row["attempts"], row["spent"], row["provider"], row["model"], row["failures"]), (1, 1.5, "codex", "gpt-5.1", 0))
        self.assertEqual(self.store.attempts(self.job), [{"at": 1000, "attempt": 1, "provider": "codex", "model": "gpt-5.1", "outcome": "succeeded", "spend": 1.5, "reason": ""}])
        self.assertEqual(self.store.get(self.job)["state"], "running")

    def test_timeout_requeues_with_backoff_and_never_completes(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        answer = self.provider_failure(receipt, reason="provider timed out")
        row = self.store.get(self.job)
        self.assertEqual((answer["state"], answer["failures"], answer["next_eligible"]), ("ready", 1, 1030))
        self.assertEqual((row["state"], row["owner"], row["expires"], row["epoch"]), ("ready", None, None, 2))
        self.assertFalse(row["publication"])
        self.assertIn("retryable provider timeout", row["reason"])
        with self.assertRaisesRegex(ContractError, "retry backoff until 1030"):
            self.store.claim(self.job, "worker-b", 60)
        self.now = 1031
        self.assertEqual(self.store.claim(self.job, "worker-b", 60)["attempts"], 1)
        self.assertEqual([e["event"] for e in self.store.db.execute("SELECT event FROM events WHERE job=? ORDER BY sequence", (self.job,))],
                         ["enqueued", "claimed", "attempt_failed", "claimed"])

    def test_quota_uses_bounded_provider_supplied_delay(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        answer = self.provider_failure(receipt, "quota", reason="429 quota", retry_after=5)
        self.assertEqual((answer["state"], answer["next_eligible"]), ("ready", 1005))
        self.assertIn("retryable provider quota: 429 quota", self.store.get(self.job)["reason"])
        self.now = 1006
        self.assertEqual(self.store.claim(self.job, "worker-b", 60)["failures"], 1)

    def test_circuit_breaker_blocks_after_attempt_budget(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        self.provider_failure(receipt, reason="first timeout")
        self.now = 1031
        receipt = self.store.claim(self.job, "worker-b", 60)
        answer = self.provider_failure(receipt, reason="second timeout")
        row = self.store.get(self.job)
        self.assertEqual((answer["state"], answer["next_eligible"]), ("blocked", None))
        self.assertEqual((row["state"], row["failures"], row["attempts"], row["next_eligible"]), ("blocked", 2, 2, None))
        self.assertIn("attempt budget exhausted: second timeout", row["reason"])
        with self.assertRaisesRegex(ContractError, "job is not ready"):
            self.store.claim(self.job, "worker-c", 60)

    def test_spend_limit_stops_new_paid_work_but_preserves_evidence(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        self.store.record_attempt(receipt, "succeeded", "codex", "gpt-5.1", spend=10)
        self.store.release(receipt, "ready", "attempt recorded")
        with self.assertRaisesRegex(ContractError, "spend limit reached: 10"):
            self.store.claim(self.job, "worker-b", 60)
        status = self.store.status()
        self.assertEqual(status["limits"], {"spend_limit": 10, "max_attempts": 2, "backoff": 30, "max_backoff": 100})
        self.assertTrue(any(reason.startswith("spend limit reached") for reason in status["jobs"][0]["admission"]))
        self.assertEqual(self.store.get(self.job)["spent"], 10)

    def test_failure_cannot_complete_or_publish(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        self.provider_failure(receipt, "failed", reason="provider crashed")
        self.assertNotIn(self.store.get(self.job)["state"], {"submitted", "accepted", "merged"})
        self.assertFalse(self.store.get(self.job)["publication"])
        with self.assertRaisesRegex(ContractError, "lease inactive"):
            self.store.begin_publication(receipt, {"head_sha": "b" * 40, "base_sha": "a" * 40, "branch": "worker/change"})

    def test_reconcile_clear_resets_circuit_but_retains_history(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        self.provider_failure(receipt, reason="first")
        self.now = 1031
        self.provider_failure(self.store.claim(self.job, "worker-b", 60), reason="second")
        blocked = self.store.get(self.job)
        self.store.reconcile(self.job, blocked["epoch"], "clear", "private:operator/retry")
        row = self.store.get(self.job)
        self.assertEqual((row["state"], row["failures"], row["next_eligible"], row["attempts"], row["spent"]), ("ready", 0, None, 2, 0))
        self.assertEqual(self.store.claim(self.job, "worker-c", 60)["failures"], 0)

    def test_version_one_database_migrates_in_place(self):
        self.store.close()
        legacy = Path(self.temp.name) / "legacy.sqlite"
        db = sqlite3.connect(legacy)
        db.executescript("""
          CREATE TABLE meta (key TEXT PRIMARY KEY, value REAL NOT NULL);
          INSERT INTO meta VALUES ('version', 1);
          INSERT INTO meta VALUES ('last_time', 0);
          CREATE TABLE jobs (
            id TEXT PRIMARY KEY, repository TEXT NOT NULL, issue INTEGER NOT NULL,
            feature TEXT NOT NULL, task_digest TEXT NOT NULL, snapshot TEXT NOT NULL,
            state TEXT NOT NULL, owner TEXT, token TEXT, epoch INTEGER NOT NULL DEFAULT 0,
            expires REAL, checkpoint TEXT, publication TEXT, reason TEXT,
            UNIQUE(repository, issue), UNIQUE(repository, feature));
          CREATE TABLE events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL,
            at REAL NOT NULL, event TEXT NOT NULL, epoch INTEGER NOT NULL, detail TEXT NOT NULL);
          CREATE TABLE requests (
            id TEXT PRIMARY KEY, dependent TEXT NOT NULL, producer TEXT NOT NULL,
            spec TEXT NOT NULL, state TEXT NOT NULL, result TEXT);
        """)
        db.execute("INSERT INTO jobs(id,repository,issue,feature,task_digest,snapshot,state) VALUES (?,?,?,?,?,?,'ready')",
                   ("example/game:FACTORY-001", "example/game", 71, "FACTORY-001", "d" * 64, json.dumps(snapshot())))
        db.commit()
        db.close()
        self.store = JobStore(legacy, lambda: self.now)
        row = self.store.get("example/game:FACTORY-001")
        self.assertEqual((row["attempts"], row["failures"], row["spent"], row["next_eligible"]), (0, 0, 0, None))
        self.assertEqual(self.store.db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0], 2)
        self.assertEqual(self.store.attempts("example/game:FACTORY-001"), [])

    def test_invalid_attempt_records_fail_closed(self):
        receipt = self.store.claim(self.job, "worker-a", 60)
        for changes in ({"reason": ""}, {"spend": -1}, {"retry_after": 0},
                        {"provider": ""}, {"model": ""}):
            with self.subTest(changes=changes):
                with self.assertRaises(ContractError):
                    self.provider_failure(receipt, **changes)
        with self.assertRaisesRegex(ContractError, "unknown provider outcome"):
            self.provider_failure(receipt, "magic", reason="x")
        self.assertEqual(self.store.get(self.job)["state"], "running")
        self.assertEqual(self.store.attempts(self.job), [])

    def test_cli_records_attempt_and_reports_limits(self):
        cli = Path(__file__).resolve().parents[1] / "cli.py"
        self.store.close()
        data = snapshot()
        data["captured_at"] = __import__("time").time()
        self.store = JobStore(self.path)
        self.store.enqueue(data)
        self.store.close()
        receipt = Path(self.temp.name) / "lease.json"
        payload = Path(self.temp.name) / "attempt.json"
        database = str(self.path)
        claim = subprocess.run([sys.executable, str(cli), "claim", "--database", database, "--owner", "codex",
                                "--receipt", str(receipt), self.job], capture_output=True, text=True)
        self.assertEqual(claim.returncode, 0, claim.stderr)
        payload.write_text(json.dumps({"outcome": "timeout", "provider": "codex", "model": "gpt-5.1", "reason": "timed out"}))
        attempt = subprocess.run([sys.executable, str(cli), "attempt", "--database", database, "--receipt", str(receipt), str(payload)],
                                 capture_output=True, text=True)
        self.assertEqual(attempt.returncode, 0, attempt.stderr)
        self.assertEqual(json.loads(attempt.stdout)["state"], "ready")
        self.assertFalse(receipt.exists())
        history = subprocess.run([sys.executable, str(cli), "history", "--database", database, self.job], capture_output=True, text=True)
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertEqual([a["outcome"] for a in json.loads(history.stdout)["attempts"]], ["timeout"])


if __name__ == "__main__":
    unittest.main()
