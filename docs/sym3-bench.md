# SYM-3 benchmark

**Primary accounting** (used in break-even and verdict): total = setup (min, decode-sufficient) + messages.
Secondary: setup (full, committed lexicon + full schema). Tertiary: setup (cached†) = 10% × setup (min). Assumes one-time decoder prefix billed at 10% of min setup tokens (not API-measured).

Minimal setup is **decode-sufficient**: all used cmd/status/kind wire mappings and format tags for the transcript (plus all format tags when `adaptive` appears).

## lifecycle_11 (11 messages)

| Format | setup (min) | messages | total (primary) | setup (full) | total (full setup) | setup (cached†) | total (cached†) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact JSON | 0 | 682 | 682 | 0 | 682 | 0.0 | 682.0 |
| pretty JSON | 0 | 849 | 849 | 0 | 849 | 0.0 | 849.0 |
| English (lossy summary) | 0 | 478 | 478 | 0 | 478 | 0.0 | 478.0 |
| English (lossless) | 0 | 686 | 686 | 0 | 686 | 0.0 | 686.0 |
| key=value text (lossless) | 0 | 691 | 691 | 0 | 691 | 0.0 | 691.0 |
| TOON (toon-format) | 0 | 805 | 805 | 0 | 805 | 0.0 | 805.0 |
| Agora envelope (arXiv:2410.11905) | 48 | 979 | 1027 | 48 | 1027 | 4.8 | 983.8 |
| SYM-2P v1 | 0 | 2719 | 2719 | 0 | 2719 | 0.0 | 2719.0 |
| SYM-2P v2 session + handshake — quoted from unmerged PR #6, not measured by this bench | 213 | 1202 | 1415 | 213 | 1415 | 21.3 | 1223.3 |
| SYM-3 delta | 250 | 349 | 599 | 524 | 873 | 25.0 | 374.0 |
| SYM-3 refs — closest prior art: Agora (arXiv:2410.11905) | 250 | 241 | 491 | 524 | 765 | 25.0 | 266.0 |
| SYM-3 positional | 251 | 256 | 507 | 524 | 780 | 25.1 | 281.1 |
| SYM-3 omit | 250 | 357 | 607 | 524 | 881 | 25.0 | 382.0 |
| SYM-3 combined | 250 | 334 | 584 | 524 | 858 | 25.0 | 359.0 |
| SYM-3 adaptive | 271 | 241 | 512 | 524 | 765 | 27.1 | 268.1 |

### Break-even (primary accounting: setup min + messages, o200k)

| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |
| --- | ---: | ---: |
| adaptive | 7 | 7 |
| combined | 8 | 8 |
| delta | 9 | 9 |
| omit | 9 | 9 |
| positional | 7 | 7 |
| refs | 7 | 7 |

## lifecycle_40 (40 messages)

| Format | setup (min) | messages | total (primary) | setup (full) | total (full setup) | setup (cached†) | total (cached†) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact JSON | 0 | 5343 | 5343 | 0 | 5343 | 0.0 | 5343.0 |
| pretty JSON | 0 | 6516 | 6516 | 0 | 6516 | 0.0 | 6516.0 |
| English (lossy summary) | 0 | 2283 | 2283 | 0 | 2283 | 0.0 | 2283.0 |
| English (lossless) | 0 | 5242 | 5242 | 0 | 5242 | 0.0 | 5242.0 |
| key=value text (lossless) | 0 | 5328 | 5328 | 0 | 5328 | 0.0 | 5328.0 |
| TOON (toon-format) | 0 | 6049 | 6049 | 0 | 6049 | 0.0 | 6049.0 |
| Agora envelope (arXiv:2410.11905) | 48 | 6449 | 6497 | 48 | 6497 | 4.8 | 6453.8 |
| SYM-2P v1 | 0 | 12925 | 12925 | 0 | 12925 | 0.0 | 12925.0 |
| SYM-3 delta | 254 | 3356 | 3610 | 524 | 3880 | 25.4 | 3381.4 |
| SYM-3 refs — closest prior art: Agora (arXiv:2410.11905) | 254 | 1463 | 1717 | 524 | 1987 | 25.4 | 1488.4 |
| SYM-3 positional | 255 | 2507 | 2762 | 524 | 3031 | 25.5 | 2532.5 |
| SYM-3 omit | 254 | 3364 | 3618 | 524 | 3888 | 25.4 | 3389.4 |
| SYM-3 combined | 254 | 2312 | 2566 | 524 | 2836 | 25.4 | 2337.4 |
| SYM-3 adaptive | 275 | 1463 | 1738 | 524 | 1987 | 27.5 | 1490.5 |

### Break-even (primary accounting: setup min + messages, o200k)

| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |
| --- | ---: | ---: |
| adaptive | 3 | 3 |
| combined | 4 | 4 |
| delta | 6 | 6 |
| omit | 6 | 6 |
| positional | 4 | 4 |
| refs | 3 | 3 |

## lifecycle_200 (200 messages)

| Format | setup (min) | messages | total (primary) | setup (full) | total (full setup) | setup (cached†) | total (cached†) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact JSON | 0 | 27363 | 27363 | 0 | 27363 | 0.0 | 27363.0 |
| pretty JSON | 0 | 33120 | 33120 | 0 | 33120 | 0.0 | 33120.0 |
| English (lossy summary) | 0 | 11439 | 11439 | 0 | 11439 | 0.0 | 11439.0 |
| English (lossless) | 0 | 26754 | 26754 | 0 | 26754 | 0.0 | 26754.0 |
| key=value text (lossless) | 0 | 27180 | 27180 | 0 | 27180 | 0.0 | 27180.0 |
| TOON (toon-format) | 0 | 30785 | 30785 | 0 | 30785 | 0.0 | 30785.0 |
| Agora envelope (arXiv:2410.11905) | 48 | 32897 | 32945 | 48 | 32945 | 4.8 | 32901.8 |
| SYM-2P v1 | 0 | 65273 | 65273 | 0 | 65273 | 0.0 | 65273.0 |
| SYM-3 delta | 254 | 17324 | 17578 | 524 | 17848 | 25.4 | 17349.4 |
| SYM-3 refs — closest prior art: Agora (arXiv:2410.11905) | 254 | 7374 | 7628 | 524 | 7898 | 25.4 | 7399.4 |
| SYM-3 positional | 255 | 13079 | 13334 | 524 | 13603 | 25.5 | 13104.5 |
| SYM-3 omit | 254 | 17364 | 17618 | 524 | 17888 | 25.4 | 17389.4 |
| SYM-3 combined | 254 | 11619 | 11873 | 524 | 12143 | 25.4 | 11644.4 |
| SYM-3 adaptive | 275 | 7374 | 7649 | 524 | 7898 | 27.5 | 7401.5 |

### Break-even (primary accounting: setup min + messages, o200k)

| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |
| --- | ---: | ---: |
| adaptive | 3 | 3 |
| combined | 4 | 4 |
| delta | 6 | 6 |
| omit | 6 | 6 |
| positional | 4 | 4 |
| refs | 3 | 3 |

## Verdict (primary accounting, o200k_base)

Under **primary** totals (decode-sufficient setup min + messages), SYM-3 **refs** totals **491** vs compact JSON **682** and lossless English **686** on lifecycle_11 (wins). **Adaptive** is **512** (also below JSON). Under **full** setup (524 + messages), refs/adaptive **765** — **above** compact JSON at 11 messages. Prior-art rows: TOON **805**, key=value text **691**, Agora envelope **1027** (messages-only baselines except Agora setup). SYM-3 **refs** is closest to Agora-style content addressing ([arXiv:2410.11905](https://arxiv.org/abs/2410.11905)). lifecycle_40/200 show larger wire savings; cached† totals use the 10% assumption only. Do not compare against English (lossy summary) for information equivalence.

