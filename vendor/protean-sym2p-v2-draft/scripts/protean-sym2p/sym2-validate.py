#!/usr/bin/env python3
"""Validate SYM-2P v2 dense packet lines.

Checks field count, token shapes, registry codes, numeric ranges, and
body s-expression shape against SPEC-V2-DRAFT.md. stdlib only.

Wire parsing lives in sym2_parse.py; this file only checks.

Usage: sym2-validate.py <packet-or-file>
Exit codes: 0 every line valid, 1 at least one invalid with a typed
diagnostic, 2 usage, IO, or configuration error.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sym2_parse import (  # noqa: E402
    ACTS, BASE, RQS, ROLES, STATES, TOKEN, check_expr, parse_all,
    split_fields,
)


def check_line(line, lineno):
    errs = []

    def err(code, msg):
        errs.append("ERR:%s line %d: %s" % (code, lineno, msg))

    fields, ferr = split_fields(line)
    if ferr:
        err("SHAPE", ferr)
        return errs
    _, pid, tk, f, t, a, st, cf, cv, body, rq, base, exp = fields
    for name, tok in (("ID", pid), ("TK", tk)):
        if not TOKEN.match(tok):
            err("TOKEN", "%s fails token pattern" % name)
    if len(tk) > 64:
        err("RANGE", "TK longer than 64 characters")
    if base and not BASE.match(base):
        err("TOKEN", "BASE is neither empty nor id:ver")
    nums = {}
    for name, raw in (("F", f), ("T", t), ("A", a), ("ST", st), ("CF", cf),
                      ("CV", cv), ("RQ", rq), ("EXP", exp)):
        if not re.fullmatch(r"\d+", raw):
            err("TYPE", "%s is not an unsigned integer" % name)
            continue
        if len(raw) > 1 and raw.startswith("0"):
            err("CANON", "%s has leading zeros" % name)
            continue
        nums[name] = int(raw)
    for name, reg, label in (("F", ROLES, "role"), ("T", ROLES, "role"),
                             ("A", ACTS, "act"), ("ST", STATES, "state"),
                             ("RQ", RQS, "request")):
        if name in nums and nums[name] not in reg:
            err("CODE", "%s=%d outside %s registry" % (name, nums[name], label))
    for name in ("CF", "CV"):
        if name in nums and not 0 <= nums[name] <= 100:
            err("RANGE", "%s=%d outside 0-100" % (name, nums[name]))
    if body.strip():
        exprs, perr = parse_all(body)
        if perr:
            err("BODY", perr)
        else:
            for e in exprs:
                cerr = check_expr(e)
                if cerr:
                    err("BODY", cerr)
    if re.search(r"\( | \)|  ", body):
        err("CANON", "BODY spacing is not canonical")
    return errs


def validate_lines(lines):
    """Validate raw lines. Returns the list of diagnostics."""
    errs = []
    for i, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        if raw != raw.strip():
            errs.append("ERR:CANON line %d: leading or trailing whitespace"
                        % i)
            continue
        for e in check_line(raw.strip(), i):
            errs.append(e)
    return errs


def main(argv):
    if len(argv) != 2:
        print("usage: sym2-validate.py <packet-or-file>", file=sys.stderr)
        return 2
    src = argv[1]
    try:
        with open(src) as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = [src]
    errs = validate_lines(lines)
    for e in errs:
        print(e, file=sys.stderr)
    if errs:
        print("%d invalid line(s)" % len(errs), file=sys.stderr)
        return 1
    print("all lines valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
