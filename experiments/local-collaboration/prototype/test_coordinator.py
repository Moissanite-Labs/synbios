import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from coordinator import (
    Coordinator,
    INTEGRATION_SURFACE,
    canonical_workspace_root,
    diff_observations,
    observe,
    overlaps,
    tree_digest,
    within,
)


def concurrent_declare(database, actor, ready, start, results):
    coordinator = Coordinator(database)
    ready.put(actor)
    if not start.wait(20):
        raise RuntimeError("Concurrent registration barrier timed out")
    try:
        declaration = coordinator.declare(actor, [], ["src/shared.txt"])
        results.put((declaration["intention"]["id"], len(declaration["conflicts"])))
    finally:
        coordinator.close()


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "target"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src/shared.txt").write_bytes(b"before\x00")
        self.database = self.base / "state.sqlite"
        self.coordinator = Coordinator(self.database, self.root)
        self.addCleanup(self.coordinator.close)

    def test_independent_processes_register_concurrently_without_lost_updates(self):
        before = observe(self.root, ["."])
        context = multiprocessing.get_context("spawn")
        ready, results, start = context.Queue(), context.Queue(), context.Event()
        workers = [context.Process(target=concurrent_declare, args=(str(self.database), "agent-" + str(i), ready, start, results)) for i in range(6)]
        try:
            for worker in workers:
                worker.start()
            for _ in workers:
                ready.get(timeout=20)
            start.set()
            responses = [results.get(timeout=30) for _ in workers]
            for worker in workers:
                worker.join(timeout=30)
                self.assertEqual(worker.exitcode, 0)
            status = self.coordinator.status()
            self.assertEqual(len(set(identity for identity, _ in responses)), 6)
            self.assertEqual(sorted(count for _, count in responses), list(range(6)))
            self.assertEqual(len(status["intentions"]), 6)
            self.assertEqual(len(status["conflicts"]), 15)
            self.assertEqual(len(status["events"]), 7)
            self.assertEqual([e["sequence"] for e in status["events"]], list(range(1, 8)))
            self.assertEqual(observe(self.root, ["."]), before)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                worker.join(timeout=5)
            ready.close()
            results.close()

    def test_stale_detects_raw_bytes_even_same_size_and_timestamp(self):
        item = self.coordinator.declare("agent", ["src/shared.txt"], [])["intention"]
        path = self.root / "src/shared.txt"
        metadata = path.stat()
        path.write_bytes(b"after!\x00")
        import os
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        self.assertEqual(path.stat().st_size, metadata.st_size)
        observation = self.coordinator.check(item["id"])
        self.assertEqual(observation["state"], "stale")
        self.assertEqual(observation["changed_paths"], ["src/shared.txt"])

    def test_directory_membership_addition_and_deletion_are_stale(self):
        item = self.coordinator.declare("agent", [], ["src"])["intention"]
        (self.root / "src/new.txt").write_text("new")
        changed = self.coordinator.check(item["id"])["changed_paths"]
        self.assertIn("src", changed)
        self.assertIn("src/new.txt", changed)
        (self.root / "src/new.txt").unlink()
        (self.root / "src/shared.txt").unlink()
        self.assertIn("src/shared.txt", self.coordinator.check(item["id"])["changed_paths"])

    def test_missing_paths_have_explicit_baseline_and_creation_is_stale(self):
        item = self.coordinator.declare("agent", [], ["future/file"])["intention"]
        self.assertEqual(item["baseline"]["future/file"], {"kind": "missing", "sha256": None})
        (self.root / "future").mkdir()
        (self.root / "future/file").write_text("created")
        self.assertEqual(self.coordinator.check(item["id"])["state"], "stale")

    def test_directory_read_write_conflicts_and_root_overlap(self):
        self.coordinator.declare("reader-1", ["src"], [])
        readers = self.coordinator.declare("reader-2", ["src/shared.txt"], [])
        self.assertEqual(readers["conflicts"], [])
        writer = self.coordinator.declare("writer", [], ["src/shared.txt"])
        self.assertEqual(len(writer["conflicts"]), 2)
        self.assertTrue(all(c["kind"] == "read/write" for c in writer["conflicts"]))
        unrelated = self.coordinator.declare("elsewhere", [], ["src2"])
        self.assertEqual(unrelated["conflicts"], [])
        root_writer = self.coordinator.declare("root", [], ["."])
        self.assertEqual(len(root_writer["conflicts"]), 4)

    def test_overlap_conservatively_handles_case_and_unicode(self):
        self.assertTrue(overlaps("Src", "src/file"))
        self.assertTrue(overlaps("caf\u00e9", "cafe\u0301/file"))
        self.assertFalse(overlaps("src", "src2/file"))

    def test_supersession_is_atomic_and_preserves_history(self):
        first = self.coordinator.declare("agent", [], ["src"])["intention"]
        before_events = len(self.coordinator.status()["events"])
        with self.assertRaises(ValueError):
            self.coordinator.declare("other", [], ["src"], first["id"])
        self.assertEqual(len(self.coordinator.status()["events"]), before_events)
        self.assertEqual(self.coordinator.get("intentions", first["id"])["status"], "active")
        second = self.coordinator.declare("agent", [], ["src"], first["id"])["intention"]
        self.assertEqual(second["revision"], 2)
        self.assertEqual(second["supersedes"], first["id"])
        self.assertEqual(self.coordinator.get("intentions", first["id"])["status"], "superseded")
        self.assertEqual(self.coordinator.status()["conflicts"], [])
        self.coordinator.finish(second["id"], "completed")
        self.assertEqual(len(self.coordinator.status()["intentions"]), 2)

    def test_failed_event_rolls_back_inserted_intention(self):
        before = self.coordinator.status()
        with patch.object(self.coordinator, "event", side_effect=RuntimeError("injected event failure")):
            with self.assertRaisesRegex(RuntimeError, "injected event failure"):
                self.coordinator.declare("agent", [], ["src"])
        after = self.coordinator.status()
        self.assertEqual(after["intentions"], before["intentions"])
        self.assertEqual(after["events"], before["events"])

    def test_alternative_metadata_and_transition_history(self):
        item = self.coordinator.declare("agent", [], ["src"])["intention"]
        ext_a = self.base / "ext-a"
        ext_a.mkdir()
        iso_parent = self.base / "iso-parent"
        iso_parent.mkdir()
        a = self.coordinator.alternative(item["id"], "candidate A", str(ext_a), candidate_digest="a" * 64)
        b = self.coordinator.alternative(
            item["id"],
            "candidate B",
            "",
            materialize_mode="copy",
            materialize_parent=str(iso_parent),
            materialize_source=str(self.root),
        )
        self.coordinator.alternative_status(a["id"], "rejected")
        self.coordinator.compare_alternative(b["id"])
        self.coordinator.alternative_status(b["id"], "accepted")
        status = self.coordinator.status()
        self.assertEqual([x["status"] for x in status["alternatives"]], ["rejected", "accepted"])
        self.assertEqual(status["alternatives"][0]["digest_source"], "caller-asserted")
        self.assertEqual(status["alternatives"][0]["isolation"]["verified"], True)
        self.assertEqual(status["intentions"][0]["status"], "active")
        self.assertEqual(status["events"][-1]["data"]["previous"], "proposed")

    def test_actor_registration_idempotent_and_inferred_names_visible(self):
        self.coordinator.declare("inferred", [], ["src"])
        first = self.coordinator.register_actor("explicit")
        second = self.coordinator.register_actor("explicit")
        self.assertEqual(first, second)
        self.assertEqual(self.coordinator.status()["actors"], [first, {"name": "inferred", "registered_at": self.coordinator.status()["intentions"][0]["created_at"], "registration": "inferred-from-intention"}])
        registered = [event for event in self.coordinator.status()["events"] if event["kind"] == "actor.registered"]
        self.assertEqual(len(registered), 1)
        with self.assertRaises(ValueError):
            self.coordinator.register_actor(" ")

    def test_unsafe_paths_and_inside_workspace_database_rejected(self):
        for path in ("../elsewhere", "/absolute", "C:/drive", "src\\file"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.coordinator.declare("agent", [], [path])
        with self.assertRaises(ValueError):
            Coordinator(self.root / "bad.sqlite", self.root)
        self.assertFalse((self.root / "bad.sqlite").exists())

    def test_symlinks_rejected_and_replacement_is_unverifiable(self):
        item = self.coordinator.declare("agent", [], ["src/shared.txt"])["intention"]
        outside = self.base / "outside.txt"
        outside.write_text("external")
        path = self.root / "src/shared.txt"
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError as error:
            self.skipTest("Symlink creation unavailable: " + str(error))
        self.assertEqual(self.coordinator.check(item["id"])["state"], "unverifiable")
        with self.assertRaises(ValueError):
            self.coordinator.declare("agent", [], ["src"])

    def test_cli_json_status_and_runtime_error(self):
        script = Path(__file__).with_name("coordinator.py")
        result = subprocess.run([sys.executable, str(script), "--db", str(self.database), "status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["protocol"], "weave.local.v1")
        expected_root = canonical_workspace_root(self.root)
        self.assertEqual(data["result"]["workspace"]["root"], expected_root)
        self.assertEqual(data["result"]["workspace"]["integration_surface"]["version"], INTEGRATION_SURFACE["version"])
        result = subprocess.run([sys.executable, str(script), "--db", str(self.database), "check", "missing"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_git_worktree_materialize_when_git_available(self):
        repo = self.base / "git-ws"
        repo.mkdir()
        (repo / "tracked.txt").write_text("v1\n")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
        init = subprocess.run(["git", "-C", str(repo), "init"], capture_output=True, text=True, env=env)
        if init.returncode != 0:
            self.skipTest("git init unavailable")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True, env=env)
        db_git = self.base / "coord-git.sqlite"
        coord = Coordinator(db_git, repo)
        self.addCleanup(coord.close)
        intent = coord.declare("agent", ["tracked.txt"], [])["intention"]
        parent = self.base / "wt-parent"
        parent.mkdir()
        alt = coord.alternative(
            intent["id"],
            "wt",
            "",
            materialize_mode="git_worktree",
            materialize_parent=str(parent),
            materialize_source=str(repo),
        )
        wt = Path(alt["isolation"]["path"])
        self.assertTrue(wt.is_dir())
        self.assertEqual((wt / "tracked.txt").read_text(), "v1\n")
        coord.compare_alternative(alt["id"])
        coord.close()

    def test_materialized_copy_binds_real_directory_to_alternative(self):
        item = self.coordinator.declare("agent", [], ["."])["intention"]
        parent = self.base / "cand-parent"
        parent.mkdir()
        alt = self.coordinator.alternative(
            item["id"],
            "fork-a",
            "",
            materialize_mode="copy",
            materialize_parent=str(parent),
            materialize_source=str(self.root),
        )
        path = Path(alt["isolation"]["path"])
        self.assertTrue(path.is_dir())
        self.assertNotEqual(path.resolve(), self.root.resolve())
        self.assertTrue(within(path, parent))
        self.assertEqual((path / "src" / "shared.txt").read_bytes(), b"before\x00")

    def test_compare_emits_evidence_before_accept_and_blocks_integrate(self):
        intent = self.coordinator.declare("agent", ["src/shared.txt"], [])["intention"]
        parent = self.base / "iso2"
        parent.mkdir()
        alt = self.coordinator.alternative(
            intent["id"],
            "mirror",
            "",
            materialize_mode="copy",
            materialize_parent=str(parent),
            materialize_source=str(self.root),
        )
        cmp_same = self.coordinator.compare_alternative(alt["id"])
        self.assertEqual(cmp_same["compare_evidence"]["diff"]["verdict"], "identical")
        self.assertTrue(cmp_same["compare_evidence"]["allow_accept"])
        fork = Path(alt["isolation"]["path"])
        (fork / "src" / "shared.txt").write_bytes(b"changed-in-isolation\n")
        cmp_diff = self.coordinator.compare_alternative(alt["id"])
        self.assertEqual(cmp_diff["compare_evidence"]["diff"]["verdict"], "different")
        self.assertFalse(cmp_diff["compare_evidence"]["allow_accept"])
        self.coordinator.alternative_status(alt["id"], "accepted")
        self.assertEqual((self.root / "src" / "shared.txt").read_bytes(), b"before\x00")

    def test_accepted_without_compare_is_rejected(self):
        intent = self.coordinator.declare("agent", [], ["src"])["intention"]
        parent = self.base / "iso3"
        parent.mkdir()
        alt = self.coordinator.alternative(
            intent["id"],
            "blind",
            "",
            materialize_mode="copy",
            materialize_parent=str(parent),
            materialize_source=str(self.root),
        )
        with self.assertRaises(ValueError):
            self.coordinator.alternative_status(alt["id"], "accepted")

    def test_materialize_parent_inside_workspace_rejected_and_no_subdirectory_created(self):
        intent = self.coordinator.declare("agent", [], ["src"])["intention"]
        inside_parent = self.root / "inside-materialize-parent"
        inside_parent.mkdir()
        before_parent = list(inside_parent.iterdir())
        with self.assertRaises(ValueError):
            self.coordinator.alternative(
                intent["id"],
                "bad-parent",
                "",
                materialize_mode="copy",
                materialize_parent=str(inside_parent),
                materialize_source=str(self.root),
            )
        self.assertEqual(list(inside_parent.iterdir()), before_parent)
        self.assertFalse(any(self.root.glob("synbios-lc-*")))

    def test_materialize_parent_under_source_tree_rejected(self):
        intent = self.coordinator.declare("agent", [], ["x"])["intention"]
        ext = self.base / "bundle"
        ext.mkdir()
        (ext / "x").mkdir()
        (ext / "x" / "f.txt").write_text("x")
        bogus_parent = ext / "x" / "nested-parent"
        bogus_parent.mkdir()
        with self.assertRaises(ValueError):
            self.coordinator.alternative(
                intent["id"],
                "nested",
                "",
                materialize_mode="copy",
                materialize_parent=str(bogus_parent),
                materialize_source=str(ext / "x"),
            )

    def test_alternative_cannot_register_as_accepted(self):
        intent = self.coordinator.declare("agent", [], ["src"])["intention"]
        parent = self.base / "iso-reg"
        parent.mkdir()
        with self.assertRaises(ValueError):
            self.coordinator.alternative(
                intent["id"],
                "skip",
                "",
                status="accepted",
                materialize_mode="copy",
                materialize_parent=str(parent),
                materialize_source=str(self.root),
            )

    def test_legacy_opaque_location_is_not_verified_isolation(self):
        intent = self.coordinator.declare("agent", [], ["src"])["intention"]
        raw = {
            "id": "legacy-alt-id",
            "intent_id": intent["id"],
            "label": "old",
            "location": "external://opaque",
            "status": "proposed",
            "candidate_digest": None,
            "digest_source": None,
        }
        self.coordinator.connection.execute("INSERT INTO alternatives VALUES (?, ?)", (raw["id"], json.dumps(raw)))
        self.coordinator.connection.commit()
        row = self.coordinator.get("alternatives", "legacy-alt-id")
        self.assertEqual(row["isolation"]["kind"], "legacy_opaque_location")
        self.assertFalse(row["isolation"]["verified"])
        with self.assertRaises(ValueError):
            self.coordinator.compare_alternative("legacy-alt-id")

    def test_tree_digest_and_diff_helpers(self):
        baseline = observe(self.root, ["src/shared.txt"])
        candidate = observe(self.root, ["src/shared.txt"])
        self.assertEqual(tree_digest(baseline), tree_digest(candidate))
        d = diff_observations(baseline, candidate)
        self.assertEqual(d["verdict"], "identical")


if __name__ == "__main__":
    unittest.main()
