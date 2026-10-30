"""Session state shared between SYM-3 encoder and decoder."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .canonical import SCHEMA_DEFAULTS, canonical_payload
from .content_store import ContentStore


@dataclass
class Sym3Session:
    """Mirrored forge session: ids, entity snapshots, content store."""

    project_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    human_id: str = ""
    artifact_id: str = ""
    task_status: str = "open"
    content: ContentStore = field(default_factory=ContentStore)
    snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)

    def ref_id(self, entity: str, raw_id: str) -> str:
        mapping = {
            "project": self.project_id,
            "task": self.task_id,
            "agent": self.agent_id,
            "human": self.human_id,
            "artifact": self.artifact_id,
        }
        if entity == "project" and raw_id == self.project_id:
            return "p"
        if entity == "task" and raw_id == self.task_id:
            return "t"
        if entity == "agent" and raw_id == self.agent_id:
            return "a"
        if entity == "human" and raw_id == self.human_id:
            return "h"
        if entity == "artifact" and raw_id == self.artifact_id:
            return "f"
        return mapping.get(entity, raw_id) or raw_id

    def resolve_ref(self, token: str) -> tuple[str, str]:
        table = {
            "p": ("project", self.project_id),
            "t": ("task", self.task_id),
            "a": ("agent", self.agent_id),
            "h": ("human", self.human_id),
            "f": ("artifact", self.artifact_id),
        }
        if token in table:
            return table[token]
        raise KeyError(token)

    def snapshot_key(self, action: str, payload: dict[str, Any]) -> str | None:
        full = canonical_payload(action, payload)
        if action in {"task.transition", "task.claim"}:
            return "task"
        if action == "task.create":
            return "task_meta"
        if action == "project.create":
            return "project"
        if action.startswith("artifact."):
            return "artifact"
        return None

    def omit_defaults(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        full = canonical_payload(action, payload)
        defaults = SCHEMA_DEFAULTS.get(action, {})
        out: dict[str, Any] = {}
        for k, v in full.items():
            if k in defaults and defaults[k] == v:
                continue
            out[k] = v
        return out

    def restore_defaults(self, action: str, sparse: dict[str, Any]) -> dict[str, Any]:
        defaults = SCHEMA_DEFAULTS.get(action, {})
        merged = {**defaults, **sparse}
        return canonical_payload(action, merged)

    def apply_message(self, action: str, payload: dict[str, Any]) -> None:
        full = canonical_payload(action, payload)
        if action == "project.create":
            pass
        elif action == "task.create":
            self.snapshots["task_meta"] = copy.deepcopy(full)
        elif action == "task.transition":
            self.task_status = full["status"]
            self.snapshots["task"] = {"task_id": full["task_id"], "status": full["status"]}
        elif action == "task.claim":
            self.task_status = "claimed"
            self.snapshots["task"] = {"task_id": full["task_id"], "status": "claimed"}
        elif action == "artifact.add":
            self.snapshots["artifact"] = copy.deepcopy(full)

    def delta_payload(self, action: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """If only task status changes, return minimal delta dict."""
        if action != "task.transition":
            return None
        full = canonical_payload(action, payload)
        prior = self.snapshots.get("task") or {"task_id": full["task_id"], "status": self.task_status}
        if prior.get("task_id") == full["task_id"] and prior.get("status") != full["status"]:
            if set(full.keys()) == {"task_id", "status"}:
                return {"status": full["status"]}
        return None
