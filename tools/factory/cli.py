#!/usr/bin/env python3
"""Inspect trusted intake or coordinator state; never start a model/provider."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from readiness import ContractError, evaluate
from store import JobStore


def claim_to(store, path, job, owner, ttl):
    """Coordinator-held receipt; the token never reaches stdout.

    The private file exists before the lease, so a claim cannot lose its token.
    """
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        try:
            receipt = store.claim(job, owner, ttl)
        except BaseException:
            os.unlink(path)
            raise
        json.dump(receipt, handle)
    return receipt


def public(receipt):
    return {k: v for k, v in receipt.items() if k != "token"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ready = sub.add_parser("readiness")
    ready.add_argument("snapshot", type=Path)
    for name in ("enqueue", "show", "recover", "status", "history"):
        command = sub.add_parser(name)
        command.add_argument("--database", type=Path, required=True)
        if name == "enqueue":
            command.add_argument("snapshot", type=Path)
        if name in ("show", "history"):
            command.add_argument("job")
    claim = sub.add_parser("claim")
    claim.add_argument("--database", type=Path, required=True)
    claim.add_argument("--owner", required=True)
    claim.add_argument("--ttl", type=int, default=300)
    claim.add_argument("--receipt", type=Path, required=True, help="new private file for the lease receipt")
    claim.add_argument("job")
    for name in ("heartbeat", "checkpoint", "request", "deliver", "release", "attempt"):
        command = sub.add_parser(name)
        command.add_argument("--database", type=Path, required=True)
        command.add_argument("--receipt", type=Path, required=True)
        if name == "heartbeat":
            command.add_argument("--ttl", type=int, default=300)
        elif name == "release":
            command.add_argument("--state", required=True)
            command.add_argument("--reason", required=True)
        else:
            if name == "deliver":
                command.add_argument("--request", required=True)
            command.add_argument("payload", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "readiness":
            result = evaluate(json.loads(args.snapshot.read_text()), time.time())
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 1
        store = JobStore(args.database)
        try:
            if args.command == "enqueue":
                result = {"job": store.enqueue(json.loads(args.snapshot.read_text()))}
            elif args.command == "status":
                result = store.status()
            elif args.command == "claim":
                result = public(claim_to(store, args.receipt, args.job, args.owner, args.ttl))
            elif args.command in ("heartbeat", "checkpoint", "request", "deliver", "release", "attempt"):
                receipt = json.loads(args.receipt.read_text())
                if args.command == "heartbeat":
                    store.heartbeat(receipt, args.ttl)
                    result = {"heartbeat": True}
                elif args.command == "checkpoint":
                    store.checkpoint(receipt, json.loads(args.payload.read_text()))
                    result = {"checkpoint": True}
                elif args.command == "request":
                    result = store.request(receipt, json.loads(args.payload.read_text()))
                elif args.command == "deliver":
                    result = store.deliver(receipt, args.request, json.loads(args.payload.read_text()))
                elif args.command == "attempt":
                    payload = json.loads(args.payload.read_text())
                    result = store.record_attempt(receipt, payload["outcome"], payload["provider"], payload["model"],
                                                  payload.get("spend", 0), payload.get("reason", ""), payload.get("retry_after"))
                else:
                    store.release(receipt, args.state, args.reason)
                    result = {"released": args.state}
                if args.command == "release" or (args.command == "request" and result["waiting"]) or (args.command == "attempt" and result["state"] != "running"):
                    args.receipt.unlink()  # the lease ended; a stale copy would only be refused
            elif args.command == "show":
                result = store.get(args.job)
                result.pop("token", None)
            elif args.command == "history":
                result = {"job": args.job, "attempts": store.attempts(args.job)}
            else:
                store.recover()
                result = {"recovered": True, "scope": "local leases only"}
            print(json.dumps(result, indent=2))
        finally:
            store.close()
        return 0
    except (ValueError, TypeError, OSError, sqlite3.Error) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
