"""Executable, non-enforcing counterpart to the proof-evidence RFC.

This is a finite experiment, not a formal proof, identity attestation, or gate.
No external toolchain or repository is invoked.
"""
from __future__ import annotations

from itertools import product
from typing import Any, Iterable, Mapping
import json


def eligible(author: str, candidate: str, reviews: Iterable[Mapping[str, str]]) -> bool:
    """Whether supplied records contain a non-author approval for this revision."""
    if not isinstance(author, str) or not author or not isinstance(candidate, str) or not candidate:
        return False
    return any(
        isinstance(review, Mapping)
        and isinstance(review.get("reviewer_id"), str)
        and bool(review["reviewer_id"])
        and review.get("state") == "APPROVED"
        and review.get("reviewer_id") != author
        and review.get("commit_id") == candidate
        for review in reviews
    )


def run_experiment() -> dict[str, Any]:
    """Exhaust a finite input space and kill each condition-removal mutant."""
    author, candidate = "author", "current"
    records = [
        {"reviewer_id": reviewer, "commit_id": revision, "state": state}
        for reviewer, revision, state in product(
            ("author", "reviewer"), ("current", "old"),
            ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"),
        )
    ]
    cases = [[], *[[r] for r in records], *[[a, b] for a, b in product(records, repeat=2)]]
    conditions = ("approval_state", "independent_reviewer", "exact_revision")
    killed: dict[str, Any] = {}
    positive = 0
    for reviews in cases:
        expected = any(r == {"reviewer_id": "reviewer", "commit_id": "current", "state": "APPROVED"} for r in reviews)
        actual = eligible(author, candidate, reviews)
        if actual != expected:
            raise AssertionError("predicate differs from enumerated reference")
        positive += int(actual)
        for omitted in conditions:
            mutant = any(
                (omitted == "approval_state" or r["state"] == "APPROVED")
                and (omitted == "independent_reviewer" or r["reviewer_id"] != author)
                and (omitted == "exact_revision" or r["commit_id"] == candidate)
                for r in reviews
            )
            if mutant != expected and omitted not in killed:
                killed[omitted] = {"reviews": reviews, "expected": expected, "mutant": mutant}
    return {
        "experiment": "synbios.exact-revision-review.v1",
        "mode": "shadow", "result": "passed" if len(killed) == 3 else "failed",
        "cases": len(cases), "positive_cases": positive,
        "negative_cases": len(cases) - positive,
        "mutants_detected": len(killed), "counterexamples": killed,
        "formal_verification": "unavailable",
        "assumptions": ["Supplied identities and review states are data, not authenticated facts."],
        "limits": [
            "Finite enumeration is not a proof over all inputs.",
            "No Bend toolchain, translated term, or independent law review is included.",
            "The predicate has no authority over Git hosts or Synbios task acceptance.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run_experiment(), indent=2))
