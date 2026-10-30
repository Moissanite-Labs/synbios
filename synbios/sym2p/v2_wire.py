"""Shape checks for SYM-2P v2 dense lines (Synbios pilot)."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from .code_table import ACTS, RQS, ROLES, STATES

_VENDOR = (
    Path(__file__).resolve().parents[2]
    / "vendor"
    / "protean-sym2p-v2-draft"
    / "scripts"
    / "protean-sym2p"
    / "sym2_parse.py"
)


def _load_vendor():
    spec = importlib.util.spec_from_file_location("_sym2_parse_vendor", _VENDOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("sym2_parse.py not found in vendor tree")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_VENDOR_MOD = None


def split_v2_fields(line: str) -> tuple[list[str] | None, str | None]:
    global _VENDOR_MOD
    if _VENDOR_MOD is None:
        _VENDOR_MOD = _load_vendor()
    return _VENDOR_MOD.split_fields(line)


def validate_v2_shape(line: str) -> None:
    """Reject malformed v2 before decode; uses vendored token/grammar rules."""
    fields, err = split_v2_fields(line.strip())
    if err:
        raise ValueError(err)
    _, _pid, tk, f, t, a, st, cf, cv, body, rq, base, exp = fields
    if len(tk) > 64:
        raise ValueError("TK longer than 64 characters")
    nums: dict[str, int] = {}
    for name, raw in (("F", f), ("T", t), ("A", a), ("ST", st), ("CF", cf), ("CV", cv), ("RQ", rq), ("EXP", exp)):
        if not re.fullmatch(r"\d+", raw):
            raise ValueError(f"{name} is not an unsigned integer")
        if len(raw) > 1 and raw.startswith("0"):
            raise ValueError(f"{name} has leading zeros")
        nums[name] = int(raw)
    for name, reg in (("F", ROLES), ("T", ROLES), ("A", ACTS), ("ST", STATES), ("RQ", RQS)):
        code = nums[name]
        if code == 0:
            continue
        if name in {"F", "T"} and 10 <= code <= 199:
            continue
        if code not in reg and not (name == "T" and code == 100):
            raise ValueError(f"{name}={code} outside registry")
    if not 0 <= nums["CF"] <= 100 or not 0 <= nums["CV"] <= 100:
        raise ValueError("CF/CV outside 0-100")
    if nums["EXP"] < 0:
        raise ValueError("EXP negative")
    if base and not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*:[A-Za-z0-9][A-Za-z0-9_.:/-]*", base):
        raise ValueError("BASE token invalid")
    if body.strip():
        mod = _VENDOR_MOD or _load_vendor()
        exprs, perr = mod.parse_all(body)
        if perr:
            raise ValueError(f"BODY: {perr}")
        for expr in exprs or []:
            head = expr[0] if expr else None
            if isinstance(head, str) and head.isdigit() and int(head) >= 33:
                continue
            cerr = mod.check_expr(expr)
            if cerr:
                raise ValueError(f"BODY: {cerr}")
