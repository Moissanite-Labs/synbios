#!/usr/bin/env python3
"""Persistent capability stewardship. Assertions and readiness are advisory only.

Uses an initialized local coordinator DB. Never executes recorded commands or
changes source. Observations are sequential, not locks or atomic snapshots.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

from coordinator import Coordinator, digest, encoded, observe, scope, verify_isolated_path

PROTOCOL = "weave.stewardship.v1"


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be nonempty text")
    return value.strip()


def strings(value, name, required=True):
    if not isinstance(value, list) or (required and not value):
        raise ValueError(name + " must be a list" + (" with entries" if required else ""))
    return sorted(set(text(v, name) for v in value))


def fields(payload, required):
    if not isinstance(payload, dict) or set(payload) != set(required.split()):
        raise ValueError("Expected exactly: " + required)


class Stewardship:
    def __init__(self, database):
        self.coordinator = Coordinator(database)
        self.db = self.coordinator.connection
        # Explicit opt-in extension only; existing coordinator tables untouched.
        self.db.execute("CREATE TABLE IF NOT EXISTS stewardship_records (sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, identity TEXT NOT NULL, data TEXT NOT NULL)")

    def close(self):
        self.coordinator.close()

    def records(self, kind):
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT data FROM stewardship_records WHERE kind=? ORDER BY sequence", (kind,))]

    def add(self, kind, record):
        self.db.execute("INSERT INTO stewardship_records(kind,identity,data) VALUES (?,?,?)",
                        (kind, record["id"], encoded(record)))
        self.coordinator.event("stewardship." + kind, record)
        return record

    def transaction(self, action, payload):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = getattr(self, "_" + action)(payload)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def latest_charters(self):
        return {r["capability_id"]: r for r in self.records("charter")}

    def _charter(self, p):
        fields(p, "capability_id actor purpose success_signals failure_signals scope peers")
        item = {key: text(p[key], key) for key in ("capability_id", "actor", "purpose")}
        for key in ("success_signals", "failure_signals", "scope", "peers"):
            item[key] = strings(p[key], key, required=key != "peers")
        item["scope"] = sorted(set(scope(s) for s in item["scope"]))
        if item["capability_id"] in item["peers"]:
            raise ValueError("A capability cannot be its own peer")
        old = self.latest_charters().get(item["capability_id"])
        item.update(id=str(uuid.uuid4()), revision=old["revision"] + 1 if old else 1,
                    supersedes=old["id"] if old else None, created_at=time.time())
        item["digest"] = digest(item)
        return self.add("charter", item)

    def proposal(self, identity):
        found = next((p for p in self.records("proposal") if p["id"] == identity), None)
        if found is None:
            raise ValueError("Unknown proposal")
        return found

    def candidate_digest(self, alternative, scopes):
        root = verify_isolated_path(self.coordinator.root, alternative["location"])
        # Explicit artifact surface; unscoped files are not verified. Directory
        # scopes include hidden/generated entries, so prefer narrow source paths.
        return digest(observe(root, scopes))

    def _propose(self, p):
        fields(p, "actor capabilities intention_id alternative_id rationale")
        actor = text(p["actor"], "actor")
        caps = strings(p["capabilities"], "capabilities")
        if len(caps) < 2:
            raise ValueError("Negotiation needs at least two capabilities")
        latest = self.latest_charters()
        if any(c not in latest for c in caps):
            raise ValueError("Unknown capability")
        charters = {c: latest[c]["digest"] for c in caps}
        if actor not in {latest[c]["actor"] for c in caps}:
            raise ValueError("Proposer must represent an affected capability")
        peers = sorted({latest[c]["actor"] for c in caps} - {actor})
        if not peers:
            raise ValueError("At least one distinct peer actor is required")
        for c in caps:
            if not latest[c]["peers"] or not set(latest[c]["peers"]) <= set(caps):
                raise ValueError("Proposal must include every declared peer of each capability")
        intention = self.coordinator.get("intentions", text(p["intention_id"], "intention_id"))
        alternative = self.coordinator.get("alternatives", text(p["alternative_id"], "alternative_id"))
        if intention["actor"] != actor or intention["status"] != "active":
            raise ValueError("Proposer needs its own active intention")
        if alternative["intent_id"] != intention["id"]:
            raise ValueError("Candidate belongs to a different intention")
        if self.coordinator.check(intention["id"])["state"] != "current":
            raise ValueError("Intention baseline is not current")
        candidate_scopes = sorted(set(intention["reads"] + intention["writes"] +
                                      [s for c in caps for s in latest[c]["scope"]]))
        item = dict(id=str(uuid.uuid4()), actor=actor, capabilities=charters, required_peers=peers,
                    intention_id=intention["id"], baseline_digest=intention["baseline_digest"],
                    alternative_id=alternative["id"], candidate_scopes=candidate_scopes,
                    source_digest=digest(observe(self.coordinator.root, candidate_scopes)),
                    candidate_digest=self.candidate_digest(alternative, candidate_scopes),
                    rationale=text(p["rationale"], "rationale"), created_at=time.time())
        item["digest"] = digest(item)
        return self.add("proposal", item)

    def freshness(self, p):
        reasons = []
        latest = self.latest_charters()
        for cap, pinned in p["capabilities"].items():
            if cap not in latest or latest[cap]["digest"] != pinned:
                reasons.append("charter_changed:" + cap)
        intention = self.coordinator.get("intentions", p["intention_id"])
        observation = self.coordinator.check(intention["id"])
        if intention["status"] != "active":
            reasons.append("intention_inactive")
        if intention["baseline_digest"] != p["baseline_digest"] or observation["state"] != "current":
            reasons.append("baseline_" + observation["state"])
        try:
            if digest(observe(self.coordinator.root, p["candidate_scopes"])) != p["source_digest"]:
                reasons.append("source_changed")
        except (OSError, ValueError):
            reasons.append("source_unverifiable")
        try:
            alternative = self.coordinator.get("alternatives", p["alternative_id"])
            if alternative["intent_id"] != p["intention_id"] or alternative["status"] == "rejected":
                reasons.append("candidate_inactive")
            if self.candidate_digest(alternative, p["candidate_scopes"]) != p["candidate_digest"]:
                reasons.append("candidate_changed")
        except (OSError, ValueError):
            reasons.append("candidate_unverifiable")
        return reasons

    def bound(self, p):
        proposal = self.proposal(text(p["proposal_id"], "proposal_id"))
        if p["proposal_digest"] != proposal["digest"] or p["candidate_digest"] != proposal["candidate_digest"]:
            raise ValueError("Response/evidence must bind the exact proposal and candidate digests")
        reasons = self.freshness(proposal)
        if reasons:
            raise ValueError("Proposal is stale: " + ", ".join(reasons))
        if any(r["proposal_id"] == proposal["id"] for r in self.records("lesson")):
            raise ValueError("Proposal is closed")
        return proposal

    def _respond(self, p):
        fields(p, "actor proposal_id proposal_digest candidate_digest decision comment")
        proposal = self.bound(p)
        actor = text(p["actor"], "actor")
        if actor not in proposal["required_peers"]:
            raise ValueError("Only a required peer may respond")
        if p["decision"] not in ("support", "revise", "decline"):
            raise ValueError("Unknown peer decision")
        return self.add("response", dict(p, actor=actor, comment=text(p["comment"], "comment"),
                                         id=str(uuid.uuid4()), created_at=time.time()))

    def _evidence(self, p):
        fields(p, "actor proposal_id proposal_digest candidate_digest kind outcome summary")
        proposal = self.bound(p)
        if p["actor"] not in [proposal["actor"]] + proposal["required_peers"]:
            raise ValueError("Evidence actor must be an affected representative")
        if p["kind"] not in ("test", "analysis", "behavior") or p["outcome"] not in ("passed", "failed", "unavailable"):
            raise ValueError("Unknown evidence kind/outcome")
        return self.add("evidence", dict(p, summary=text(p["summary"], "summary"),
                                         id=str(uuid.uuid4()), created_at=time.time(), assertion_only=True))

    def _close(self, p):
        fields(p, "actor proposal_id lesson")
        proposal = self.proposal(text(p["proposal_id"], "proposal_id"))
        if p["actor"] != proposal["actor"]:
            raise ValueError("Only the proposer may record closure")
        if any(r["proposal_id"] == proposal["id"] for r in self.records("lesson")):
            raise ValueError("Proposal already closed")
        final_observation = self.check(proposal["id"])
        return self.add("lesson", dict(p, lesson=text(p["lesson"], "lesson"),
                                       id=str(uuid.uuid4()), created_at=time.time(),
                                       final_observation=final_observation,
                                       closure="advisory_ready" if final_observation["ready"] else "not_ready"))

    def check(self, identity):
        p = self.proposal(identity)
        reasons = self.freshness(p)
        replies = {r["actor"]: r for r in self.records("response") if r["proposal_id"] == identity}
        evidence = [r for r in self.records("evidence") if r["proposal_id"] == identity]
        missing = [a for a in p["required_peers"] if a not in replies or replies[a]["decision"] != "support"]
        # Each kind's latest assertion controls readiness; a later failure cannot
        # be hidden by retaining an earlier pass. These remain caller assertions.
        latest_evidence = {(r["actor"], r["kind"]): r for r in evidence}
        passed = (any(r["kind"] in ("test", "behavior") and r["outcome"] == "passed" for r in latest_evidence.values())
                  and all(r["outcome"] == "passed" for r in latest_evidence.values()))
        lessons = [r for r in self.records("lesson") if r["proposal_id"] == identity]
        return dict(proposal=p, stale_reasons=reasons, required_peer_responses=missing,
                    responses=list(replies.values()), evidence=evidence, lessons=lessons,
                    ready=not reasons and not missing and passed and not lessons,
                    authority="Advisory caller assertions; no authenticated approval, execution or integration authority.")

    def resume(self, capability=None):
        charters = self.latest_charters()
        if capability is not None and capability not in charters:
            raise ValueError("Unknown capability")
        proposals = [p for p in self.records("proposal") if capability is None or capability in p["capabilities"]]
        return dict(workspace=self.coordinator.workspace,
                    charters=[v for k, v in charters.items() if capability is None or k == capability],
                    proposals=[self.check(p["id"]) for p in proposals], protocol=PROTOCOL)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("charter", "propose", "respond", "evidence", "close"):
        sub.add_parser(command).add_argument("file", help="JSON payload file")
    sub.add_parser("check").add_argument("proposal_id")
    sub.add_parser("resume").add_argument("--capability")
    args = parser.parse_args(argv)
    steward = None
    try:
        steward = Stewardship(args.db)
        if args.command == "check":
            result = steward.check(args.proposal_id)
        elif args.command == "resume":
            result = steward.resume(args.capability)
        else:
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = steward.transaction(args.command, payload)
        print(encoded(dict(protocol=PROTOCOL, ok=True, result=result)))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(encoded(dict(protocol=PROTOCOL, ok=False, error=str(error))))
        return 1
    finally:
        if steward is not None:
            steward.close()


if __name__ == "__main__":
    sys.exit(main())
