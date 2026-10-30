# SYM-2P/2.0: draft specification

Status: DRAFT for review. Nothing here is normative. It becomes a proposal
for the reviewing team to reshape before any merge.

## 1. Why v2

SYM-2P v1 speaks JSON but thinks in English. The packet fields are English
prose inside string values: "scope: implement SYM-2P/1.0 sections 3-5 only".
A receiver that is a model must parse human language to understand a machine
message. That is the handicap. The full intention is laid out in
VISION.md.

v2 moves the language to symbols. Packet content is codes, numbers, and
structured expressions. English is a render target, not the source. A
translator script converts packets to human-readable English for operators.

What v2 keeps from v1: one packet per line in durable text artifacts, a
versioned wire format, and a validator with exit codes 0 (valid), 1
(invalid), 2 (usage or IO error).

## 2. Wire format

One packet is one line. Fields are positional, separated by `|` (U+007C).
There are no key names on the wire. Field order is fixed:

```
V|ID|TK|F|T|A|ST|CF|CV|BODY|RQ|BASE|EXP
```

| #   | Field   | Type          | Meaning                                    |
| --- | ------- | ------------- | ------------------------------------------ |
| 1   | V       | literal `2`   | wire version                               |
| 2   | ID      | token         | packet id, e.g. `b441`                     |
| 3   | TK      | token         | thread key                                 |
| 4   | F       | integer       | sender role code (section 3)               |
| 5   | T       | integer       | recipient role code (section 3)            |
| 6   | A       | integer       | act code (section 3)                       |
| 7   | ST      | integer       | state code (section 3)                     |
| 8   | CF      | 0-100         | confidence                                 |
| 9   | CV      | 0-100         | coverage                                   |
| 10  | BODY    | s-expressions | symbolic payload, may be empty (section 4) |
| 11  | RQ      | integer       | request code, 0 means none (section 3)     |
| 12  | BASE    | token         | base reference `id:ver`, empty means none  |
| 13  | EXP     | integer       | expiry in seconds, 0 means none            |

A token matches `[A-Za-z0-9][A-Za-z0-9_.:/-]*`. The BODY field never
contains `|`.

Thread keys stay tokens. Threads are instance data, not shared
vocabulary: coding them would need per-thread allocation, which is a
separate protocol. TK is limited to 64 characters.

## 3. Code registries

Every categorical value is an integer. Code 0 is reserved in each registry
and means unset. Unknown codes are invalid.

Roles:

| Code   | Role             |
| ------ | ---------------- |
| 1      | coordinator      |
| 2      | builder          |
| 3      | verifier         |
| 4      | scout            |
| 5      | critic           |
| 6      | operator (human) |

Acts:

| Code   | Act         |
| ------ | ----------- |
| 1      | assign      |
| 2      | acknowledge |
| 3      | assert      |
| 4      | update      |
| 5      | receipt     |
| 6      | challenge   |
| 7      | dispute     |
| 8      | authorize   |
| 9      | query       |
| 10     | inform      |

States:

| Code   | State      |
| ------ | ---------- |
| 1      | proposed   |
| 2      | accepted   |
| 3      | rejected   |
| 4      | verified   |
| 5      | open       |
| 6      | closed     |
| 7      | superseded |
| 8      | expired    |

Requests (RQ):

| Code   | Meaning                  |
| ------ | ------------------------ |
| 0      | none                     |
| 1      | acknowledgement required |
| 2      | verification required    |

## 4. Body language

The BODY field holds zero or more s-expressions. Each expression is an
operation applied to arguments:

```
expr := '(' op arg* ')'
arg  := number | symbol | expr
```

A symbol matches `[A-Za-z][A-Za-z0-9_./-]*` or is `*` (meaning all).
Symbols are case-sensitive. Core vocabulary is lowercase by convention.
Numbers are unsigned integers.

Operation codes:

| Code   | Operation   | Shape              | Meaning                                             |
| ------ | ----------- | ------------------ | --------------------------------------------------- |
| 10     | scope       | `(10 target impl)` | what the packet covers                              |
| 11     | constraint  | `(11 constraint)`  | a hard limit                                        |
| 12     | accept      | `(12 accept)`      | acceptance criterion                                |
| 20     | impl        | `(20 unit range)`  | implement a unit over a range                       |
| 21     | nomod       | `(21 paths)`       | modify no paths                                     |
| 22     | exit        | `(22 prog ok bad)` | program exits `ok` on valid input, `bad` on invalid |

Units such as `sec` are plain symbols, not opcodes. They appear as
arguments, for example `(20 sec (3 5))`, never as expression heads.

Example body:

```
(10 sym-2p/1.0 (20 sec (3 5)))(11 (21 *))(12 (22 validator 0 1))
```

Read as: scope is SYM-2P/1.0, implement sections 3 to 5. It modifies no
existing paths. The validator exits 0 on valid input and 1 on invalid.

## 5. Canonical form

- Exactly 13 `|`-separated fields.
- Integers carry no leading zeros.
- Inside BODY, exactly one space separates elements. No space follows `(`
  or precedes `)`.
- No leading or trailing whitespace on the line.

## 6. Validation

A v2 validator MUST reject a line when any of these hold, with a typed
diagnostic:

- Field count is not 13, or V is not `2`.
- ID, TK, or BASE fail the token pattern. BASE is neither empty nor
  `id:ver` shaped.
- F, T, A, ST, or RQ fall outside their registries.
- CF or CV fall outside 0-100; EXP is negative.
- BODY has unbalanced parentheses, an unknown opcode, or a malformed
  expression.

Exit codes follow v1: 0 means every line valid, 1 means at least one
invalid with a typed diagnostic, 2 means usage, IO, or configuration
error.

## 7. The renderer

`sym2-render.py` converts v2 packets to human-readable English. It is the
script that turns the internal language into human syntax. Operators read
the rendered form. Agents read the wire form. The renderer is
informative, never normative: two renderers may word the same packet
differently, but they MUST NOT change its meaning. Wire parsing is shared
with the validator through `sym2_parse.py` so the grammar lives in one
place.

## 8. Density

The v1 brief packet template is 481 bytes. The same packet in v2:

```
2|b441|mr1|1|2|1|1|88|70|(10 sym-2p/1.0 (20 sec (3 5)))(11 (21 *))(12 (22 validator 0 1))|1|mr1:v1|40
```

That line is 101 bytes. The density gain comes from three removals: key
names, English prose, and JSON punctuation. The same packet is 4.8x
smaller than the 481-byte v1 template. The line above is the exact
output of `sym2-migrate.py` on the v1 template.

## 9. Migration

- v1 (SYM-2P/1.0) stays normative and untouched. This draft does not
  change it.
- v2 is a new wire version, not an upgrade path. A line starting with
  `2|` is v2; v1 lines are JSON objects.
- The kit lock still pins v1.0.0 until this draft is accepted and merged.
- v1-to-v2 translation tooling ships as `sym2-migrate.py`: structured
  fields map through the registries, and English cond strings map
  through known patterns. A cond with no known pattern fails loudly
  rather than being guessed at. Emitted symbols are case-folded to
  lowercase, per the core-vocabulary convention in section 4.

## 10. Open items for reviewers

- Opcode registry governance. Proposed policy: codes 1-99 are core and
  owned by this spec. Codes 100-999 are domain extensions, allocated by
  pull request with reviewer approval. No code is ever reused once
  assigned. The registry lives in sections 3 and 4 of this draft, and
  the renderer MUST cover every assigned code.
- Thread keys stay tokens per section 2. The ambiguity is resolved:
  instance data is not coded.
- Transport signing (v1 open item O-1) is still open and carries over.
  Tracked as issue #15.
- The renderer vocabulary will grow with the opcode registry. The two
  MUST stay in sync.
