#!/usr/bin/env python3
"""Read-only workspace observations and cooperative intentions; Python stdlib only."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import sys
import time
import unicodedata
import uuid

PROTOCOL = "weave.local.v1"
ALTERNATIVE_STATES = ("proposed", "testing", "accepted", "rejected")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def within(path, parent):
    return path == parent or parent in path.parents


def scope(value):
    if not value or "\\" in value or ":" in value:
        raise ValueError("Scopes must be relative POSIX paths, with no backslash or colon")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("Scopes cannot be absolute or contain '..'")
    return str(p)


def overlaps(a, b):
    # Conservative across common case-insensitive/Unicode-normalizing filesystems.
    # This can report extra conflicts on case-sensitive filesystems.
    a, b = (unicodedata.normalize("NFC", value).casefold() for value in (a, b))
    return a == "." or b == "." or a == b or a.startswith(b + "/") or b.startswith(a + "/")


def observe(root, scopes):
    """Capture raw content and directory membership. Not an atomic filesystem snapshot."""
    entries = {}

    def visit(path, key):
        if key in entries:
            return
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            entries[key] = {"kind": "missing", "sha256": None}
            return
        if stat.S_ISLNK(mode):
            raise ValueError("Symlink in observed scope: " + key)
        if stat.S_ISDIR(mode):
            names = sorted(child.name for child in path.iterdir())
            entries[key] = {"kind": "directory", "sha256": digest(names)}
            for name in names:
                visit(path / name, name if key == "." else key + "/" + name)
        elif stat.S_ISREG(mode):
            h = hashlib.sha256()
            # lstat above does not eliminate the check/open race. See README.
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    h.update(chunk)
            entries[key] = {"kind": "file", "sha256": h.hexdigest()}
        else:
            raise ValueError("Only regular files/directories are supported: " + key)

    for item in sorted(set(scopes)):
        relative = Path(*PurePosixPath(item).parts)
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("Symlink in observed scope: " + item)
        visit(root / relative, item)
    return entries


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace (singleton INTEGER PRIMARY KEY CHECK(singleton=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intentions (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alternatives (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
"""


class Coordinator:
    def __init__(self, database, root=None):
        self.database = Path(database).expanduser().resolve()
        if root is not None:
            root = Path(root).expanduser().resolve(strict=True)
            if not root.is_dir():
                raise ValueError("Workspace must be an existing directory")
            if within(self.database, root):
                raise ValueError("Database must be outside target workspace")
        elif not self.database.is_file():
            raise ValueError("Initialize the database first")
        self.connection = sqlite3.connect(str(self.database), timeout=30, isolation_level=None)
        self.connection.execute("PRAGMA busy_timeout=30000")
        try:
            if root is not None:
                self.connection.executescript(SCHEMA)
                self.connection.execute("BEGIN IMMEDIATE")
                try:
                    row = self.connection.execute("SELECT data FROM workspace WHERE singleton=1").fetchone()
                    if row:
                        current = json.loads(row[0])
                        if current["root"] != str(root):
                            raise ValueError("Database already belongs to a different workspace")
                    else:
                        current = {"id": str(uuid.uuid4()), "root": str(root), "protocol": PROTOCOL}
                        self.connection.execute("INSERT INTO workspace VALUES (1, ?)", (encoded(current),))
                        self.event("workspace.initialized", current)
                    self.connection.commit()
                except Exception:
                    self.connection.rollback()
                    raise
            row = self.connection.execute("SELECT data FROM workspace WHERE singleton=1").fetchone()
            if not row:
                raise ValueError("Database has no workspace")
            self.workspace = json.loads(row[0])
            if self.workspace["protocol"] != PROTOCOL:
                raise ValueError("Unsupported stored protocol")
            self.root = Path(self.workspace["root"])
            if self.root.resolve() != self.root or within(self.database, self.root):
                raise ValueError("Workspace root changed or database is inside target")
            if not self.root.is_dir():
                raise ValueError("Workspace root is unavailable")
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def event(self, kind, data):
        self.connection.execute("INSERT INTO events(time, kind, data) VALUES (?, ?, ?)", (time.time(), kind, encoded(data)))

    def rows(self, table):
        return [json.loads(row[0]) for row in self.connection.execute("SELECT data FROM " + table + " ORDER BY rowid")]

    def get(self, table, identity):
        row = self.connection.execute("SELECT data FROM " + table + " WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ValueError("Unknown " + table + " ID: " + identity)
        return json.loads(row[0])

    def save(self, table, item):
        self.connection.execute("UPDATE " + table + " SET data=? WHERE id=?", (encoded(item), item["id"]))

    def conflicts(self, intentions):
        active = [item for item in intentions if item["status"] == "active"]
        result = []
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                for left, right, kind in (("writes", "writes", "write/write"), ("writes", "reads", "write/read"), ("reads", "writes", "read/write")):
                    for x in a[left]:
                        for y in b[right]:
                            if overlaps(x, y):
                                result.append({"left_intent": a["id"], "right_intent": b["id"], "left_path": x, "right_path": y, "kind": kind})
        return result

    def declare(self, actor, reads, writes, supersedes=None):
        if not actor.strip():
            raise ValueError("Actor cannot be blank")
        reads, writes = sorted(set(map(scope, reads))), sorted(set(map(scope, writes)))
        if not reads and not writes:
            raise ValueError("At least one read or write scope is required")
        baseline = observe(self.root, reads + writes)
        item = {"id": str(uuid.uuid4()), "workspace_id": self.workspace["id"], "actor": actor,
                "revision": 1, "supersedes": supersedes, "reads": reads, "writes": writes,
                "baseline": baseline, "baseline_digest": digest(baseline), "status": "active", "created_at": time.time()}
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if supersedes:
                previous = self.get("intentions", supersedes)
                if previous["actor"] != actor or previous["status"] != "active":
                    raise ValueError("Can supersede only an active intention of the same asserted actor")
                item["revision"] = previous["revision"] + 1
                previous["status"] = "superseded"
                self.save("intentions", previous)
                self.event("intention.superseded", {"id": supersedes, "by": item["id"]})
            self.connection.execute("INSERT INTO intentions VALUES (?, ?)", (item["id"], encoded(item)))
            self.event("intention.declared", item)
            conflicts = [c for c in self.conflicts(self.rows("intentions")) if item["id"] in (c["left_intent"], c["right_intent"])]
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return {"intention": item, "conflicts": conflicts}

    def stale(self, item):
        try:
            current = observe(self.root, item["reads"] + item["writes"])
        except (OSError, ValueError) as error:
            return {"intent_id": item["id"], "state": "unverifiable", "error": str(error)}
        changed = [key for key in sorted(set(current) | set(item["baseline"])) if current.get(key) != item["baseline"].get(key)]
        return {"intent_id": item["id"], "state": "stale" if changed else "current", "changed_paths": changed,
                "observed_digest": digest(current), "observed_at": time.time()}

    def check(self, identity):
        return self.stale(self.get("intentions", identity))

    def status(self):
        # A consistent database view; filesystem observations happen after this transaction.
        self.connection.execute("BEGIN")
        try:
            intentions, alternatives = self.rows("intentions"), self.rows("alternatives")
            events = [{"sequence": s, "time": t, "kind": k, "data": json.loads(d)} for s, t, k, d in self.connection.execute("SELECT sequence,time,kind,data FROM events ORDER BY sequence")]
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        actors = {event["data"]["name"]: event["data"] for event in events if event["kind"] == "actor.registered"}
        for intention in intentions:
            actors.setdefault(intention["actor"], {"name": intention["actor"], "registered_at": intention["created_at"], "registration": "inferred-from-intention"})
        return {"workspace": self.workspace, "actors": sorted(actors.values(), key=lambda item: item["name"]), "intentions": intentions, "alternatives": alternatives,
                "conflicts": self.conflicts(intentions), "observations": [self.stale(i) for i in intentions if i["status"] == "active"], "events": events}

    def register_actor(self, name):
        if not name.strip():
            raise ValueError("Actor name cannot be blank")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = [json.loads(row[0]) for row in self.connection.execute("SELECT data FROM events WHERE kind='actor.registered' ORDER BY sequence")]
            record = next((item for item in existing if item["name"] == name), None)
            if record is None:
                record = {"name": name, "registered_at": time.time(), "registration": "explicit"}
                self.event("actor.registered", record)
            self.connection.commit()
            return record
        except Exception:
            self.connection.rollback()
            raise

    def finish(self, identity, status):
        if status not in ("completed", "abandoned"):
            raise ValueError("Invalid intention terminal status")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            item = self.get("intentions", identity)
            if item["status"] != "active":
                raise ValueError("Only active intentions can finish")
            item["status"] = status
            self.save("intentions", item)
            self.event("intention." + status, {"id": identity})
            self.connection.commit()
            return item
        except Exception:
            self.connection.rollback()
            raise

    def alternative(self, identity, label, location, status="proposed", candidate_digest=None):
        if status not in ALTERNATIVE_STATES or not label.strip() or not location.strip():
            raise ValueError("Alternative requires label, location and valid status")
        if candidate_digest is not None and (len(candidate_digest) != 64 or any(c not in "0123456789abcdef" for c in candidate_digest)):
            raise ValueError("Candidate digest must be lowercase SHA-256 hex")
        item = {"id": str(uuid.uuid4()), "intent_id": identity, "label": label, "location": location,
                "status": status, "candidate_digest": candidate_digest, "digest_source": "caller-asserted" if candidate_digest else None}
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.get("intentions", identity)
            self.connection.execute("INSERT INTO alternatives VALUES (?, ?)", (item["id"], encoded(item)))
            self.event("alternative.registered", item)
            self.connection.commit()
            return item
        except Exception:
            self.connection.rollback()
            raise

    def alternative_status(self, identity, status):
        if status not in ALTERNATIVE_STATES:
            raise ValueError("Invalid alternative status")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            item = self.get("alternatives", identity)
            previous = item["status"]
            item["status"] = status
            self.save("alternatives", item)
            self.event("alternative.status", {"id": identity, "previous": previous, "status": status})
            self.connection.commit()
            return item
        except Exception:
            self.connection.rollback()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite path outside target workspace")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("root")
    declare = commands.add_parser("declare")
    declare.add_argument("--actor", required=True)
    declare.add_argument("--read", action="append", default=[])
    declare.add_argument("--write", action="append", default=[])
    declare.add_argument("--supersedes")
    commands.add_parser("check").add_argument("id")
    commands.add_parser("status")
    commands.add_parser("register-actor").add_argument("name")
    finish = commands.add_parser("finish")
    finish.add_argument("id")
    finish.add_argument("--status", required=True, choices=("completed", "abandoned"))
    alternative = commands.add_parser("alternative")
    alternative.add_argument("id")
    alternative.add_argument("--label", required=True)
    alternative.add_argument("--location", required=True)
    alternative.add_argument("--status", choices=ALTERNATIVE_STATES, default="proposed")
    alternative.add_argument("--candidate-digest")
    alternative_status = commands.add_parser("alternative-status")
    alternative_status.add_argument("id")
    alternative_status.add_argument("--status", required=True, choices=ALTERNATIVE_STATES)
    args = parser.parse_args(argv)
    coordinator = None
    try:
        coordinator = Coordinator(args.db, args.root if args.command == "init" else None)
        if args.command == "init":
            result = {"workspace": coordinator.workspace}
        elif args.command == "declare":
            result = coordinator.declare(args.actor, args.read, args.write, args.supersedes)
        elif args.command == "check":
            result = coordinator.check(args.id)
        elif args.command == "status":
            result = coordinator.status()
        elif args.command == "register-actor":
            result = coordinator.register_actor(args.name)
        elif args.command == "finish":
            result = coordinator.finish(args.id, args.status)
        elif args.command == "alternative":
            result = coordinator.alternative(args.id, args.label, args.location, args.status, args.candidate_digest)
        else:
            result = coordinator.alternative_status(args.id, args.status)
        print(encoded({"protocol": PROTOCOL, "ok": True, "result": result}))
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(encoded({"protocol": PROTOCOL, "ok": False, "error": str(error)}))
        return 1
    finally:
        if coordinator:
            coordinator.close()


if __name__ == "__main__":
    sys.exit(main())
