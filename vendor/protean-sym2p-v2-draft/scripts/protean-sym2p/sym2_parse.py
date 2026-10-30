#!/usr/bin/env python3
"""Shared parsing for SYM-2P v2 dense packets. stdlib only.

Both sym2-render.py and sym2-validate.py import from here so the wire
grammar lives in exactly one place.
"""
import re

TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
BASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*:[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
SYM = re.compile(r"^(?:\*|[A-Za-z][A-Za-z0-9_./-]*)$")

ROLES = {0: "reserved", 1: "coordinator", 2: "builder", 3: "verifier",
         4: "scout", 5: "critic", 6: "operator"}
ACTS = {0: "none", 1: "assign", 2: "acknowledge", 3: "assert", 4: "update",
        5: "receipt", 6: "challenge", 7: "dispute", 8: "authorize",
        9: "query", 10: "inform"}
STATES = {0: "none", 1: "proposed", 2: "accepted", 3: "rejected",
          4: "verified", 5: "open", 6: "closed", 7: "superseded",
          8: "expired"}
RQS = {0: "none", 1: "acknowledgement required", 2: "verification required"}
UNITS = {"sec": "sections"}

FIELD_NAMES = ["V", "ID", "TK", "F", "T", "A", "ST", "CF", "CV",
               "BODY", "RQ", "BASE", "EXP"]


def tokenize(text):
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tokens.append(c)
            i += 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse_all(text):
    """Parse concatenated s-expressions. Returns (exprs, error)."""

    def parse(pos):
        pos += 1  # consume '('
        items = []
        while pos < len(tokens) and tokens[pos] != ")":
            if tokens[pos] == "(":
                sub, pos = parse(pos)
                items.append(sub)
            else:
                items.append(tokens[pos])
                pos += 1
        if pos >= len(tokens):
            raise ValueError("unbalanced parentheses")
        return items, pos + 1

    tokens = tokenize(text)
    try:
        exprs, pos = [], 0
        while pos < len(tokens):
            if tokens[pos] != "(":
                raise ValueError("top-level atom outside expression")
            expr, pos = parse(pos)
            exprs.append(expr)
    except ValueError as ex:
        return None, str(ex)
    return exprs, None


def is_num(t):
    return isinstance(t, str) and t.isdigit()


def is_sym(t):
    return isinstance(t, str) and bool(SYM.match(t))


def as_op(e, want):
    if not isinstance(e, list) or not e or e[0] != str(want):
        return "want (%d ...)" % want
    return check_expr(e)


def check_expr(e):
    """Check one s-expression against the opcode grammar. None means ok."""
    if not isinstance(e, list) or not e:
        return "empty expression"
    if not (isinstance(e[0], str) and e[0].isdigit()):
        return "expression head is not an opcode"
    op, args = int(e[0]), e[1:]
    if op == 10:
        if len(args) != 2 or not is_sym(args[0]):
            return "scope wants (10 target impl)"
        return as_op(args[1], 20)
    if op == 11:
        if len(args) != 1:
            return "constraint wants (11 constraint)"
        return as_op(args[0], 21)
    if op == 12:
        if len(args) != 1:
            return "accept wants (12 accept)"
        return as_op(args[0], 22)
    if op == 20:
        if len(args) != 2 or not is_sym(args[0]):
            return "impl wants (20 unit range)"
        r = args[1]
        if not (isinstance(r, list) and len(r) == 2
                and is_num(r[0]) and is_num(r[1])):
            return "range wants (lo hi)"
        return None
    if op == 21:
        if len(args) != 1 or not is_sym(args[0]):
            return "nomod wants (21 paths)"
        return None
    if op == 22:
        if len(args) != 3 or not is_sym(args[0]) \
                or not is_num(args[1]) or not is_num(args[2]):
            return "exit wants (22 prog ok bad)"
        return None
    return "unknown opcode %d" % op


def split_fields(line):
    """Split a v2 line into 13 fields. Returns (fields, error)."""
    fields = line.split("|")
    if len(fields) != 13:
        return None, "want 13 fields, have %d" % len(fields)
    if fields[0] != "2":
        return None, "want wire version 2"
    return fields, None
