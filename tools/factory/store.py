"""Single-host coordinator-owned SQLite leases with fencing and publication holds.

Workers receive lease receipts; they must not have database or merge credentials.
This module launches no provider, shell command, GitHub operation or host service.

A lease holder may request a bounded experiment from another job's owner.
The dependent job then waits; only a verified result bound to the same producer
task, checkpointed head and source identity returns it to ready, exactly once.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid

from readiness import ContractError, canonical, digest, evaluate, nonempty, overlaps, require, sha, strings, validate_task

BINDING = {"release", "module_sha256", "cpu", "address_space", "load_lifetime"}
VERIFICATION = {"original-bytes", "natural-runtime"}
RESULT = {"task_digest", "base_sha", "head_sha", "report_sha256", "evidence_ref", "status", "binding", "verified", "hypotheses"}


def binding(value):
    require(isinstance(value, dict) and set(value) == BINDING and all(nonempty(value[k]) for k in BINDING) and sha(value["module_sha256"], 64),
            "source binding needs release, module_sha256, cpu, address_space and load_lifetime")
    return value


def verified(value, label):
    strings(value, label)
    require(set(value) <= VERIFICATION, label + " must name original-bytes and/or natural-runtime")
    return sorted(value)


def _amount(value, label):
    require(type(value) in (int, float) and value == value and value not in (float("inf"), float("-inf")), label + " must be a finite number")
    require(value >= 0, label + " must not be negative")
    return float(value)


class JobStore:
    def __init__(self, path, clock=time.time, max_running=None, spend_limit=None, max_attempts=3, backoff=30, max_backoff=3600):
        require(max_running is None or (type(max_running) is int and max_running >= 1), "running cap must be a positive integer")
        require(spend_limit is None or (type(spend_limit) in (int, float) and spend_limit == spend_limit and 0 < spend_limit < float("inf")), "spend limit must be a positive finite number")
        require(type(max_attempts) is int and max_attempts >= 1, "retry attempt budget must be a positive integer")
        require(type(backoff) in (int, float) and 0 < backoff < float("inf"), "backoff must be a positive finite number")
        require(type(max_backoff) in (int, float) and backoff <= max_backoff < float("inf"), "max backoff must be finite and at least the base backoff")
        self.clock, self.max_running = clock, max_running
        self.spend_limit, self.max_attempts = spend_limit, max_attempts
        self.backoff, self.max_backoff = backoff, max_backoff
        self.db = sqlite3.connect(Path(path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value REAL NOT NULL);
          INSERT OR IGNORE INTO meta VALUES ('version', 2);
          INSERT OR IGNORE INTO meta VALUES ('last_time', 0);
          CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, repository TEXT NOT NULL, issue INTEGER NOT NULL,
            feature TEXT NOT NULL, task_digest TEXT NOT NULL, snapshot TEXT NOT NULL,
            state TEXT NOT NULL, owner TEXT, token TEXT, epoch INTEGER NOT NULL DEFAULT 0,
            expires REAL, checkpoint TEXT, publication TEXT, reason TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
            provider TEXT, model TEXT, spent REAL NOT NULL DEFAULT 0, next_eligible REAL,
            UNIQUE(repository, issue), UNIQUE(repository, feature));
          CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL,
            at REAL NOT NULL, event TEXT NOT NULL, epoch INTEGER NOT NULL, detail TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY, dependent TEXT NOT NULL, producer TEXT NOT NULL,
            spec TEXT NOT NULL, state TEXT NOT NULL, result TEXT);
          CREATE TABLE IF NOT EXISTS attempts (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL,
            at REAL NOT NULL, attempt INTEGER NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            outcome TEXT NOT NULL, spend REAL NOT NULL, reason TEXT NOT NULL);
        """)
        self._migrate()
        require(self.db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0] == 2, "unsupported store version")

    def _migrate(self):
        version = self.db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]
        if version == 2:
            return
        require(version == 1, "unsupported store version")
        # Version 1 stores predate durable attempt/spend records. Add columns in
        # place so an existing coordinator database survives this upgrade.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        for name, declaration in (("attempts", "INTEGER NOT NULL DEFAULT 0"), ("failures", "INTEGER NOT NULL DEFAULT 0"),
                                  ("provider", "TEXT"), ("model", "TEXT"), ("spent", "REAL NOT NULL DEFAULT 0"),
                                  ("next_eligible", "REAL")):
            if name not in columns:
                self.db.execute("ALTER TABLE jobs ADD COLUMN " + name + " " + declaration)
        self.db.execute("UPDATE meta SET value=2 WHERE key='version'")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            now = self.clock()
            last = self.db.execute("SELECT value FROM meta WHERE key='last_time'").fetchone()[0]
            require(type(now) in (int, float) and now >= last and now < float("inf"), "clock moved backwards or is invalid")
            self.db.execute("UPDATE meta SET value=? WHERE key='last_time'", (now,))
            yield now
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def record(self, job, now, event, epoch, detail=None):
        self.db.execute("INSERT INTO events(job,at,event,epoch,detail) VALUES (?,?,?,?,?)", (job, now, event, epoch, canonical(detail or {})))

    def get(self, job):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
        require(row is not None, "unknown job")
        return dict(row)

    def enqueue(self, snapshot):
        task = validate_task(snapshot.get("task"))
        repository = task["repository"].casefold()
        key = repository + ":" + task["feature_id"]
        with self.transaction() as now:
            result = evaluate(snapshot, now)
            require(result["ready"], "; ".join(result["reasons"]))
            existing = self.db.execute("SELECT * FROM jobs WHERE id=? OR (repository=? AND issue=?)", (key, repository, task["issue"])).fetchone()
            if existing:
                require(existing["id"] == key and existing["task_digest"] == digest(task), "duplicate issue or changed task needs explicit reconciliation")
                require(existing["state"] not in {"running", "publishing"}, "cannot refresh an owned job")
                self.db.execute("UPDATE jobs SET snapshot=? WHERE id=?", (canonical(snapshot), key))
                self.record(key, now, "refreshed", existing["epoch"])
            else:
                self.db.execute("INSERT INTO jobs(id,repository,issue,feature,task_digest,snapshot,state) VALUES (?,?,?,?,?,?,'ready')", (key, repository, task["issue"], task["feature_id"], digest(task), canonical(snapshot)))
                self.record(key, now, "enqueued", 0)
        return key

    def _recover(self, now):
        for row in self.db.execute("SELECT * FROM jobs WHERE state IN ('running','publishing') AND expires<=?", (now,)).fetchall():
            publishing = row["state"] == "publishing"
            state = "blocked" if publishing else "ready"
            reason = "publication outcome unknown; reconcile remote state" if publishing else "lease expired"
            self.db.execute("UPDATE jobs SET state=?,owner=NULL,token=NULL,expires=NULL,epoch=epoch+1,reason=? WHERE id=?", (state, reason, row["id"]))
            self.record(row["id"], now, "expired", row["epoch"] + 1, {"state": state, "reason": reason})

    def recover(self):
        with self.transaction() as now:
            self._recover(now)

    def claim(self, job, owner, ttl=300):
        require(nonempty(owner), "owner required")
        require(type(ttl) is int and 1 <= ttl <= 3600, "lease TTL must be 1..3600 seconds")
        with self.transaction() as now:
            self._recover(now)
            row = self.get(job)
            require(row["state"] == "ready", "job is not ready" + (": " + row["reason"] if row["reason"] else ""))
            snapshot = json.loads(row["snapshot"])
            reasons = self._admission(row, snapshot, now)
            require(not reasons, "; ".join(reasons))
            token, epoch = uuid.uuid4().hex, row["epoch"] + 1
            self.db.execute("UPDATE jobs SET state='running',owner=?,token=?,epoch=?,expires=?,reason=NULL WHERE id=?", (owner, token, epoch, now + ttl, job))
            self.record(job, now, "claimed", epoch, {"owner": owner})
            return {"job": job, "owner": owner, "token": token, "epoch": epoch, "expires": now + ttl, "task_digest": row["task_digest"], "base_sha": snapshot["base_sha"], "checkpoint": json.loads(row["checkpoint"]) if row["checkpoint"] else None,
                    "attempts": row["attempts"], "failures": row["failures"], "provider": row["provider"], "model": row["model"], "spent": row["spent"],
                    "results": self._results(job), "requests": self._open_requests(job)}

    def _admission(self, row, snapshot, now):
        """Reasons a ready job cannot be claimed now."""
        reasons = list(evaluate(snapshot, now)["reasons"])
        if row["next_eligible"] is not None and row["next_eligible"] > now:
            reasons.append("retry backoff until %s" % row["next_eligible"])
        if self.spend_limit is not None and row["spent"] >= self.spend_limit:
            reasons.append("spend limit reached: %s of %s" % (row["spent"], self.spend_limit))
        for other in self.db.execute("SELECT * FROM jobs WHERE repository=? AND id!=?", (row["repository"], row["id"])):
            # Unknown publication outcomes remain reserved even after expiry/cancellation.
            if other["state"] in {"running", "publishing", "submitted"} or other["publication"]:
                if overlaps(snapshot["task"]["scope"]["paths"], json.loads(other["snapshot"])["task"]["scope"]["paths"]):
                    reasons.append("scope already reserved by " + other["id"])
        if self.max_running is not None:
            running = self.db.execute("SELECT count(*) FROM jobs WHERE state IN ('running','publishing')").fetchone()[0]
            if running >= self.max_running:
                reasons.append("running cap reached: %d of %d" % (running, self.max_running))
        return reasons

    def _requests(self, column, job, state):
        return [dict(r) for r in self.db.execute("SELECT * FROM requests WHERE " + column + "=? AND state=? ORDER BY id", (job, state))]

    def _results(self, job):
        """Selected source-bound metadata for the dependent worker; never tokens or the database."""
        return [{"request": r["id"], "producer": r["producer"], **{k: v for k, v in json.loads(r["spec"]).items() if k != "producer_task_digest"}, "result": json.loads(r["result"])}
                for r in self._requests("dependent", job, "fulfilled")]

    def _open_requests(self, job):
        # Fulfilled experiments are never handed to a resumed producer again.
        return [{"request": r["id"], "dependent": r["dependent"], **{k: v for k, v in json.loads(r["spec"]).items() if k != "producer_task_digest"}}
                for r in self._requests("producer", job, "open") if self.get(r["dependent"])["state"] != "cancelled"]

    def _owned(self, receipt, now):
        row = self.get(receipt["job"])
        require(row["state"] in {"running", "publishing"} and row["expires"] > now, "lease inactive or expired")
        require(all(row[key] == receipt.get(key) for key in ("owner", "token", "epoch", "task_digest")), "stale or foreign lease receipt")
        return row

    def heartbeat(self, receipt, ttl=300):
        require(type(ttl) is int and 1 <= ttl <= 3600, "invalid TTL")
        with self.transaction() as now:
            self._owned(receipt, now)
            self.db.execute("UPDATE jobs SET expires=? WHERE id=?", (now + ttl, receipt["job"]))
            self.record(receipt["job"], now, "heartbeat", receipt["epoch"])

    def record_attempt(self, receipt, outcome, provider, model, spend=0, reason="", retry_after=None):
        """Persist one bounded provider attempt and its consumed budget.

        A timeout/quota/failure never completes the job: it releases the lease,
        enters a bounded backoff and, after the configured attempt budget, opens
        the circuit as blocked instead of retrying forever. A success resets the
        consecutive-failure count but leaves attempt/spend history intact.
        """
        require(outcome in {"succeeded", "timeout", "quota", "failed"}, "unknown provider outcome")
        require(nonempty(provider) and nonempty(model), "provider and model version required")
        spend = _amount(spend, "spend")
        require(outcome == "succeeded" or nonempty(reason), "provider failure needs a reason")
        require(retry_after is None or (type(retry_after) in (int, float) and 0 < retry_after < float("inf")), "retry delay must be a positive finite number")
        with self.transaction() as now:
            row = self._owned(receipt, now)
            require(row["state"] == "running", "cannot record a provider attempt during publication")
            attempt, total = row["attempts"] + 1, row["spent"] + spend
            self.db.execute("INSERT INTO attempts(job,at,attempt,provider,model,outcome,spend,reason) VALUES (?,?,?,?,?,?,?,?)",
                            (receipt["job"], now, attempt, provider, model, outcome, spend, reason))
            if outcome == "succeeded":
                self.db.execute("UPDATE jobs SET attempts=?,provider=?,model=?,spent=?,failures=0,next_eligible=NULL WHERE id=?",
                                (attempt, provider, model, total, receipt["job"]))
                self.record(receipt["job"], now, "attempt", receipt["epoch"], {"attempt": attempt, "outcome": outcome, "spend": spend})
                return {"attempt": attempt, "outcome": outcome, "state": row["state"], "failures": 0, "spend": total, "next_eligible": None}
            failures, epoch = row["failures"] + 1, row["epoch"] + 1
            if failures >= self.max_attempts:
                state, next_eligible = "blocked", None
                stop = "attempt budget exhausted: " + reason
                self.db.execute("UPDATE jobs SET state='blocked',owner=NULL,token=NULL,expires=NULL,epoch=?,attempts=?,failures=?,provider=?,model=?,spent=?,next_eligible=NULL,reason=? WHERE id=?",
                                (epoch, attempt, failures, provider, model, total, stop, receipt["job"]))
                self.record(receipt["job"], now, "circuit_opened", epoch, {"attempt": attempt, "outcome": outcome, "failures": failures, "reason": stop})
            else:
                delay = min(self.max_backoff, retry_after if retry_after is not None else self.backoff * 2 ** min(failures - 1, 30))
                state, next_eligible = "ready", now + delay
                stop = "retryable provider " + outcome + ": " + reason
                self.db.execute("UPDATE jobs SET state='ready',owner=NULL,token=NULL,expires=NULL,epoch=?,attempts=?,failures=?,provider=?,model=?,spent=?,next_eligible=?,reason=? WHERE id=?",
                                (epoch, attempt, failures, provider, model, total, next_eligible, stop, receipt["job"]))
                self.record(receipt["job"], now, "attempt_failed", epoch, {"attempt": attempt, "outcome": outcome, "failures": failures, "spend": spend, "next_eligible": next_eligible})
            return {"attempt": attempt, "outcome": outcome, "state": state, "failures": failures, "spend": total, "next_eligible": next_eligible}

    def attempts(self, job):
        """Attempt/spend history; retained across restarts and never tokens."""
        self.get(job)
        return [dict(row) for row in self.db.execute("SELECT at,attempt,provider,model,outcome,spend,reason FROM attempts WHERE job=? ORDER BY sequence", (job,))]

    def checkpoint(self, receipt, checkpoint):
        require(isinstance(checkpoint, dict) and sha(checkpoint.get("base_sha")) and sha(checkpoint.get("head_sha")) and nonempty(checkpoint.get("next_step")), "checkpoint requires exact base/head and next step")
        require(len(canonical(checkpoint).encode()) <= 65536, "checkpoint exceeds 64KiB; store logs separately")
        with self.transaction() as now:
            self._owned(receipt, now)
            self.db.execute("UPDATE jobs SET checkpoint=? WHERE id=?", (canonical(checkpoint), receipt["job"]))
            self.record(receipt["job"], now, "checkpoint", receipt["epoch"], {"digest": digest(checkpoint)})

    def begin_publication(self, receipt, intent):
        require(isinstance(intent, dict) and set(intent) == {"head_sha", "base_sha", "branch"} and sha(intent["head_sha"]) and sha(intent["base_sha"]) and nonempty(intent["branch"]), "invalid publication intent")
        with self.transaction() as now:
            row = self._owned(receipt, now)
            if row["publication"]:
                require(json.loads(row["publication"]) == intent, "publication intent is immutable")
                return
            self.db.execute("UPDATE jobs SET state='publishing',publication=? WHERE id=?", (canonical(intent), receipt["job"]))
            self.record(receipt["job"], now, "publication_started", receipt["epoch"], intent)

    def release(self, receipt, state, reason):
        require(state in {"ready", "blocked", "submitted"} and nonempty(reason), "invalid release")
        with self.transaction() as now:
            row = self._owned(receipt, now)
            require(not row["publication"] or state in {"blocked", "submitted"}, "publication must be reconciled before requeue")
            require(state != "submitted" or row["publication"], "submission requires publication intent")
            self.db.execute("UPDATE jobs SET state=?,owner=NULL,token=NULL,expires=NULL,epoch=epoch+1,next_eligible=NULL,reason=? WHERE id=?", (state, reason, receipt["job"]))
            self.record(receipt["job"], now, "released", receipt["epoch"] + 1, {"state": state, "reason": reason})

    def cancel(self, job, reason):
        require(nonempty(reason), "cancellation reason required")
        with self.transaction() as now:
            row = self.get(job)
            self.db.execute("UPDATE jobs SET state='cancelled',owner=NULL,token=NULL,expires=NULL,epoch=epoch+1,reason=? WHERE id=?", (reason, job))
            self.record(job, now, "cancelled", row["epoch"] + 1, {"reason": reason})

    def reconcile(self, job, expected_epoch, outcome, evidence_ref):
        """Trusted coordinator only, after checking remote processes/branches/PRs.

        'clear' permits retry only when no old publisher or active PR remains.
        'accepted' records completion only after independent exact-head merge checks.
        This local store cannot authenticate those external assertions.
        """
        require(outcome in {"clear", "accepted"} and nonempty(evidence_ref), "reconciliation evidence required")
        with self.transaction() as now:
            row = self.get(job)
            require(row["epoch"] == expected_epoch and row["state"] in {"blocked", "submitted", "cancelled"}, "reconciliation state changed")
            require(outcome != "accepted" or row["publication"], "cannot accept without a publication")
            if outcome == "clear":
                self.db.execute("UPDATE jobs SET state='ready',publication=NULL,epoch=epoch+1,failures=0,next_eligible=NULL,reason=? WHERE id=?", (evidence_ref, job))
            else:
                self.db.execute("UPDATE jobs SET state='accepted',publication=NULL,epoch=epoch+1,reason=? WHERE id=?", (evidence_ref, job))
            self.record(job, now, "reconciled", row["epoch"] + 1, {"outcome": outcome, "evidence_ref": evidence_ref})

    def request(self, receipt, specs):
        """Dependent lease holder asks other jobs' owners for bounded experiments.

        Each spec: producer job ID, one question, exact source binding and the
        required verification kinds. Repeats are idempotent; already fulfilled
        experiments are returned instead of dispatched again.
        """
        require(isinstance(specs, list) and 1 <= len(specs) <= 8, "request 1..8 bounded experiments")
        with self.transaction() as now:
            row = self._owned(receipt, now)
            require(row["state"] == "running", "cannot request during publication")
            ids = []
            for spec in specs:
                require(isinstance(spec, dict) and set(spec) == {"producer", "question", "binding", "verified"}, "request needs producer, question, binding and verified")
                require(nonempty(spec["question"]) and len(spec["question"]) <= 2000, "request needs one bounded question")
                producer = self.get(spec["producer"])
                require(producer["id"] != row["id"] and producer["repository"] == row["repository"], "producer must be another job in the same repository")
                require(producer["state"] not in {"cancelled", "accepted"}, "producer job cannot run experiments")
                body = {"question": spec["question"], "binding": binding(spec["binding"]), "verified": verified(spec["verified"], "required verification"), "producer_task_digest": producer["task_digest"]}
                key = digest({"dependent": row["id"], "producer": producer["id"], **body})
                if self.db.execute("INSERT OR IGNORE INTO requests VALUES (?,?,?,?,'open',NULL)", (key, row["id"], producer["id"], canonical(body))).rowcount:
                    self.record(row["id"], now, "requested", receipt["epoch"], {"request": key, "producer": producer["id"]})
                ids.append(key)
            waiting = [i for i in ids if self.db.execute("SELECT state FROM requests WHERE id=?", (i,)).fetchone()[0] == "open"]
            if waiting:
                reason = "awaiting experiments: " + ", ".join(sorted(waiting))
                self.db.execute("UPDATE jobs SET state='waiting',owner=NULL,token=NULL,expires=NULL,epoch=epoch+1,reason=? WHERE id=?", (reason, row["id"]))
                self.record(row["id"], now, "waiting", receipt["epoch"] + 1, {"requests": sorted(waiting)})
            return {"requests": ids, "waiting": sorted(waiting), "results": [r for r in self._results(row["id"]) if r["request"] in ids]}

    def deliver(self, receipt, request, result):
        """Producer lease holder returns one result; only a matching verified one unblocks."""
        with self.transaction() as now:
            row = self._owned(receipt, now)
            found = self.db.execute("SELECT * FROM requests WHERE id=?", (request,)).fetchone()
            require(found is not None and found["producer"] == row["id"], "unknown request for this producer")
            spec = json.loads(found["spec"])
            require(isinstance(result, dict) and set(result) == RESULT, "result fields are missing or unknown")
            if found["state"] == "fulfilled":
                require(json.loads(found["result"]) == result, "request already fulfilled by a different result")
                return {"request": request, "satisfied": True, "duplicate": True}
            require(result["task_digest"] == row["task_digest"] == spec["producer_task_digest"], "result is for a different producer task revision")
            require(result["binding"] == spec["binding"], "result source binding does not match the request")
            checkpoint = json.loads(row["checkpoint"]) if row["checkpoint"] else {}
            require(sha(result["head_sha"]) and sha(result["base_sha"]) and result["head_sha"] == checkpoint.get("head_sha") and result["base_sha"] == checkpoint.get("base_sha"), "result head/base must match the producer's current checkpoint")
            require(sha(result["report_sha256"], 64) and nonempty(result["evidence_ref"]), "result lacks report hash or evidence reference")
            require(result["status"] in {"verified", "failed", "truncated"}, "invalid result status")
            strings(result["hypotheses"], "hypotheses", True)
            strings(result["verified"], "verified", True)
            require(set(result["verified"]) <= VERIFICATION, "unknown verification kind")
            missing = sorted(set(spec["verified"]) - set(result["verified"]))
            if result["status"] != "verified" or missing:
                reason = "result " + result["status"] + ("; missing verification: " + ", ".join(missing) if missing else "")
                self.record(row["id"], now, "result_rejected", receipt["epoch"], {"request": request, "reason": reason, "report_sha256": result["report_sha256"]})
                return {"request": request, "satisfied": False, "reason": reason}
            self.db.execute("UPDATE requests SET state='fulfilled',result=? WHERE id=?", (canonical(result), request))
            self.record(row["id"], now, "result_delivered", receipt["epoch"], {"request": request, "report_sha256": result["report_sha256"]})
            dependent = self.get(found["dependent"])
            if dependent["state"] == "waiting" and not self._requests("dependent", dependent["id"], "open"):
                self.db.execute("UPDATE jobs SET state='ready',epoch=epoch+1,reason=NULL WHERE id=?", (dependent["id"],))
                self.record(dependent["id"], now, "unblocked", dependent["epoch"] + 1, {"request": request})
            return {"request": request, "satisfied": True, "duplicate": False}

    def status(self):
        """Inspectable ownership without tokens. Leases are records, not process liveness."""
        now = self.clock()
        self.db.execute("BEGIN")
        try:
            jobs = []
            for row in self.db.execute("SELECT * FROM jobs ORDER BY id").fetchall():
                snapshot, checkpoint = json.loads(row["snapshot"]), json.loads(row["checkpoint"]) if row["checkpoint"] else None
                leased = row["state"] in {"running", "publishing"}
                jobs.append({
                    "job": row["id"], "state": row["state"], "owner": row["owner"], "epoch": row["epoch"], "reason": row["reason"],
                    "lease": {"recorded": leased, "expires": row["expires"], "expired": leased and row["expires"] <= now},
                    "process_liveness": "unknown: the store records leases, not processes",
                    "scope": snapshot["task"]["scope"],
                    "checkpoint": {"present": checkpoint is not None, "head_sha": checkpoint and checkpoint["head_sha"], "next_step": checkpoint and checkpoint["next_step"]},
                    "attempts": row["attempts"], "failures": row["failures"], "provider": row["provider"], "model": row["model"],
                    "spent": row["spent"], "next_eligible": row["next_eligible"],
                    "admission": self._admission(row, snapshot, now) if row["state"] == "ready" else [],
                    "waiting_on": [r["id"] for r in self._requests("dependent", row["id"], "open")],
                    "requested_of": [r["id"] for r in self._requests("producer", row["id"], "open")],
                })
            return {"schema": "neptune.factory-status.v1", "at": now,
                    "limits": {"spend_limit": self.spend_limit, "max_attempts": self.max_attempts,
                               "backoff": self.backoff, "max_backoff": self.max_backoff},
                    "jobs": jobs}
        finally:
            self.db.execute("COMMIT")
