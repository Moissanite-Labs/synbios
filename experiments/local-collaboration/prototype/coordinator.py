#!/usr/bin/env python3
"""Read-only workspace observations and cooperative intentions; Python stdlib only."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import sys
import time
import unicodedata
import uuid

PROTOCOL = "weave.local.v1"
INTEGRATION_SURFACE = {
    "name": "synbios.local_collab.exo_harness",
    "version": "0.1.0",
    "exo_swarm_design_pull_requests": {"1189": "task_contract", "1190": "plan_execution", "1191": "real_engine_e2e"},
    "notes": "Wraps Exo swarm contracts from open PRs; adapters do not import exo until those land on main.",
}
MATERIALIZE_MODES = (None, "copy", "git_worktree", "directory")
ALTERNATIVE_STATES = ("proposed", "testing", "accepted", "rejected")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def within(path, parent):
    """True if ``path`` is ``parent`` or a descendant directory of ``parent``.

    Canonicalizes with ``expanduser().resolve()`` (non-strict) on both sides so
    platform path aliases (e.g. macOS ``/var`` → ``/private/var``) and ``..``
    segments match membership checks used by the coordinator and tests.
    """
    p = Path(path).expanduser().resolve()
    q = Path(parent).expanduser().resolve()
    return p == q or q in p.parents


def canonical_workspace_root(candidate):
    """Absolute workspace root string as stored after init (expanduser + resolve).

    Matches :meth:`Coordinator.__init__` registration of a new root: an initial
    path alias is resolved to a real directory (e.g. macOS ``/var`` → ``/private/var``).
    """
    return str(Path(candidate).expanduser().resolve(strict=True))


def canonical_database_path(candidate):
    """Absolute database path as assigned in :meth:`Coordinator.__init__`.

    Uses ``expanduser`` then ``resolve`` without ``strict`` so the sqlite file
    path is canonical even before the file exists (new database).
    """
    return Path(candidate).expanduser().resolve()


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


def tree_digest(entries):
    """Deterministic digest of an observe() map for exact-artifact comparisons."""
    return digest(entries)


def diff_observations(baseline, candidate):
    """Classify paths from two observe() maps (same scope keys)."""
    keys = sorted(set(baseline) | set(candidate))
    same, different, only_a, only_b = [], [], [], []
    for key in keys:
        ba, ca = baseline.get(key), candidate.get(key)
        if ba is None:
            only_b.append(key)
        elif ca is None:
            only_a.append(key)
        elif ba == ca:
            same.append(key)
        else:
            different.append(key)
    verdict = "identical" if not different and not only_a and not only_b else "different"
    return {"same_paths": same, "different_paths": different, "missing_in_candidate": only_a, "missing_in_baseline": only_b, "verdict": verdict}


def _git_rev_parse_toplevel(path):
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError as error:
        raise ValueError("git unavailable for worktree isolation: " + str(error)) from error
    if completed.returncode != 0:
        raise ValueError("materialize git_worktree requires source inside a git work tree: " + (completed.stderr or "").strip())
    return Path(completed.stdout.strip()).resolve()


def materialize_isolated_tree(mode, source_root, dest_parent, label):
    """Create an isolated directory tree; returns (resolved_dest_path, isolation_meta)."""
    if mode not in MATERIALIZE_MODES or mode is None:
        raise ValueError("Invalid materialize mode")
    dest_parent = Path(dest_parent).expanduser().resolve(strict=True)
    if not dest_parent.is_dir():
        raise ValueError("Materialization parent must be an existing directory")
    safe = "".join((c if c.isalnum() or c in "-_" else "_") for c in label).strip("_") or "alt"
    safe = safe[:48]
    suffix = uuid.uuid4().hex[:10]
    name = f"synbios-lc-{safe}-{suffix}"
    dest = dest_parent / name
    source_root = Path(source_root).expanduser().resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("Materialize source must be an existing directory")
    if dest.exists():
        raise ValueError("Unexpected existing path for materialized candidate")
    if mode == "copy":
        shutil.copytree(source_root, dest, symlinks=False, dirs_exist_ok=False)
        return dest, {"kind": "materialized_copy", "mode": "copy", "source": str(source_root), "path": str(dest)}
    if mode == "directory":
        dest.mkdir(parents=False)
        return dest, {"kind": "materialized_directory", "mode": "directory", "source": None, "path": str(dest)}
    if mode == "git_worktree":
        repo_root = _git_rev_parse_toplevel(source_root)
        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(dest), "HEAD"],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            stderr = (error.stderr or error.stdout or "").strip()
            raise ValueError("git worktree add failed: " + stderr) from error
        return dest, {
            "kind": "materialized_git_worktree",
            "mode": "git_worktree",
            "source": str(source_root),
            "git_common_dir": str(repo_root),
            "path": str(dest),
        }
    raise ValueError("Unsupported materialize mode")


def verify_isolated_path(workspace_root, path):
    """Candidate trees must live outside the shared workspace and be real directories."""
    root = Path(workspace_root).resolve()
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        raise ValueError("Isolation path must be an existing directory") from None
    if not resolved.is_dir():
        raise ValueError("Isolation path must be an existing directory")
    if resolved == root or within(resolved, root):
        raise ValueError("Alternative tree must be outside the coordinator workspace root")
    return resolved


def verify_materialize_parent(workspace_root, parent, source):
    """Parent must be outside the workspace, exist, and not lie on or under the source tree (copy safety)."""
    parent_res = verify_isolated_path(workspace_root, parent)
    try:
        source_res = Path(source).expanduser().resolve(strict=True)
    except (OSError, ValueError, RuntimeError) as error:
        raise ValueError("Materialize source must be an existing directory") from error
    if not source_res.is_dir():
        raise ValueError("Materialize source must be an existing directory")
    if parent_res == source_res:
        raise ValueError("materialize_parent must not be the same directory as materialize_source")
    if within(parent_res, source_res):
        raise ValueError("materialize_parent must not be inside the materialize source tree")
    return parent_res, source_res


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace (singleton INTEGER PRIMARY KEY CHECK(singleton=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intentions (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alternatives (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
"""


class Coordinator:
    def __init__(self, database, root=None):
        self.database = canonical_database_path(database)
        if root is not None:
            root = Path(canonical_workspace_root(root))
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
                        current = {
                            "id": str(uuid.uuid4()),
                            "root": str(root),
                            "protocol": PROTOCOL,
                            "integration_surface": dict(INTEGRATION_SURFACE),
                        }
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
            if self.workspace.get("integration_surface", {}).get("version") != INTEGRATION_SURFACE["version"]:
                self.workspace["integration_surface"] = dict(INTEGRATION_SURFACE)
                self.connection.execute("BEGIN IMMEDIATE")
                try:
                    self.connection.execute("UPDATE workspace SET data=? WHERE singleton=1", (encoded(self.workspace),))
                    self.connection.commit()
                except Exception:
                    self.connection.rollback()
                    raise
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

    def _coerce_alternative_record(self, item):
        """Attach isolation metadata; legacy rows had only an opaque location string."""
        if item.get("isolation"):
            return item
        loc = item.get("location") or ""
        try:
            resolved = verify_isolated_path(self.root, loc)
            isolation = {"kind": "external_directory", "mode": None, "verified": True, "path": str(resolved), "source": None}
        except ValueError:
            isolation = {
                "kind": "legacy_opaque_location",
                "verified": False,
                "path": None,
                "mode": None,
                "source": None,
                "raw_location": loc,
            }
        merged = dict(item)
        merged["isolation"] = isolation
        return merged

    def rows(self, table):
        result = []
        for row in self.connection.execute("SELECT data FROM " + table + " ORDER BY rowid"):
            item = json.loads(row[0])
            if table == "alternatives":
                item = self._coerce_alternative_record(item)
            result.append(item)
        return result

    def get(self, table, identity):
        row = self.connection.execute("SELECT data FROM " + table + " WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ValueError("Unknown " + table + " ID: " + identity)
        item = json.loads(row[0])
        if table == "alternatives":
            item = self._coerce_alternative_record(item)
        return item

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

    def _baseline_paths_for_compare(self, intention):
        scopes = intention["reads"] + intention["writes"]
        baseline = intention["baseline"]
        if "." in scopes:
            return dict(baseline)
        selected = {}
        for key, value in baseline.items():
            if key in scopes:
                selected[key] = value
                continue
            for s in scopes:
                if key == s or key.startswith(s + "/"):
                    selected[key] = value
                    break
        return selected

    def compare_alternative(self, identity):
        """Emit exact-artifact comparison evidence without writing the workspace tree."""
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            item = self.get("alternatives", identity)
            if not item.get("isolation") or not item["isolation"].get("verified"):
                raise ValueError("Compare requires a verified isolated directory; use materialize or an external directory outside the workspace")
            intent = self.get("intentions", item["intent_id"])
            resolved = Path(item["isolation"]["path"]).resolve()
            baseline_map = self._baseline_paths_for_compare(intent)
            candidate_map = observe(resolved, intent["reads"] + intent["writes"])
            baseline_digest = tree_digest(baseline_map)
            candidate_digest_computed = tree_digest(candidate_map)
            diff = diff_observations(baseline_map, candidate_map)
            allow_accept = diff["verdict"] == "identical" and not diff["different_paths"] and not diff["missing_in_candidate"] and not diff["missing_in_baseline"]
            evidence = {
                "integration_surface_version": INTEGRATION_SURFACE["version"],
                "protocol": PROTOCOL,
                "baseline_tree_digest": baseline_digest,
                "candidate_tree_digest": candidate_digest_computed,
                "diff": diff,
                "allow_accept": allow_accept,
                "compared_at": time.time(),
            }
            item["compare_evidence"] = evidence
            self.save("alternatives", item)
            self.event("alternative.compared", {"alternative_id": identity, "allow_accept": allow_accept})
            self.connection.commit()
            return {"alternative": self.get("alternatives", identity), "compare_evidence": evidence}
        except Exception:
            self.connection.rollback()
            raise

    def alternative(self, identity, label, location, status="proposed", candidate_digest=None, materialize_mode=None, materialize_parent=None, materialize_source=None):
        if status not in ALTERNATIVE_STATES or not label.strip():
            raise ValueError("Alternative requires a non-empty label and valid status")
        if status == "accepted":
            raise ValueError("Cannot register an alternative as accepted before compare evidence exists")
        if candidate_digest is not None and (len(candidate_digest) != 64 or any(c not in "0123456789abcdef" for c in candidate_digest)):
            raise ValueError("Candidate digest must be lowercase SHA-256 hex")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.get("intentions", identity)
            isolation = None
            resolved_path = None
            if materialize_mode:
                if materialize_mode not in ("copy", "git_worktree", "directory"):
                    raise ValueError("materialize_mode must be copy, git_worktree, or directory")
                parent = materialize_parent
                if parent is None:
                    raise ValueError("materialize_parent is required when materialize_mode is set")
                source = materialize_source if materialize_source is not None else self.root
                parent_path, source_path = verify_materialize_parent(self.root, parent, source)
                dest, meta = materialize_isolated_tree(materialize_mode, source_path, parent_path, label)
                resolved_path = verify_isolated_path(self.root, dest)
                isolation = {
                    "kind": meta["kind"],
                    "mode": meta["mode"],
                    "verified": True,
                    "path": str(resolved_path),
                    "source": meta.get("source"),
                    "git_common_dir": meta.get("git_common_dir"),
                }
                location = str(resolved_path)
            else:
                if not (location or "").strip():
                    raise ValueError("Alternative requires a non-empty location or materialize_mode")
                resolved_path = verify_isolated_path(self.root, location)
                isolation = {"kind": "external_directory", "mode": None, "verified": True, "path": str(resolved_path), "source": None}
                location = str(resolved_path)
            item = {
                "id": str(uuid.uuid4()),
                "intent_id": identity,
                "label": label,
                "location": location,
                "status": status,
                "candidate_digest": candidate_digest,
                "digest_source": "caller-asserted" if candidate_digest else None,
                "isolation": isolation,
                "integration_surface_version": INTEGRATION_SURFACE["version"],
                "compare_evidence": None,
            }
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
            if status == "accepted":
                evidence = item.get("compare_evidence")
                if not evidence or "baseline_tree_digest" not in evidence:
                    raise ValueError("accepted requires prior successful compare_alternative (stored compare evidence)")
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
    alternative.add_argument("--location", default="")
    alternative.add_argument(
        "--materialize",
        choices=("copy", "git_worktree", "directory"),
        help="Create an isolated tree under --materialize-parent (copy of --materialize-source, detached git worktree, or empty directory)",
    )
    alternative.add_argument("--materialize-parent", help="Existing directory outside the workspace where the isolated tree is created")
    alternative.add_argument("--materialize-source", help="Source root for copy or worktree (defaults to workspace root)")
    alternative.add_argument("--status", choices=ALTERNATIVE_STATES, default="proposed")
    alternative.add_argument("--candidate-digest")
    alternative_status = commands.add_parser("alternative-status")
    alternative_status.add_argument("id")
    alternative_status.add_argument("--status", required=True, choices=ALTERNATIVE_STATES)
    commands.add_parser("compare-alternative").add_argument("id")
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
            if args.materialize and not args.materialize_parent:
                raise ValueError("--materialize-parent is required when --materialize is set")
            if not args.materialize and not (args.location or "").strip():
                raise ValueError("Either --location (existing dir outside workspace) or --materialize is required")
            result = coordinator.alternative(
                args.id,
                args.label,
                args.location,
                args.status,
                args.candidate_digest,
                materialize_mode=args.materialize,
                materialize_parent=args.materialize_parent,
                materialize_source=args.materialize_source,
            )
        elif args.command == "compare-alternative":
            result = coordinator.compare_alternative(args.id)
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
