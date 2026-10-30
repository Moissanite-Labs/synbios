# SYM-3 benchmark

Decoder setup includes the format header (`sym3/1`), **transcript-minimal lexicon** (non–self-describing wire tokens only), and **positional schema rows for commands used**. **Setup (cached)** = 10% × setup (min); Assumes one-time decoder prefix billed at 10% of input token price (not measured on an API).

## lifecycle_11 (11 messages)

| Format | setup full | setup min | setup cached† | messages | total (full setup) | total (cached setup)† | amortized full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact JSON | 0 | 0 | 0.0 | 682 | 682 | 682.0 | 62.0 |
| pretty JSON | 0 | 0 | 0.0 | 849 | 849 | 849.0 | 77.2 |
| English (lossy summary) | 0 | 0 | 0.0 | 478 | 478 | 478.0 | 43.5 |
| English (lossless) | 0 | 0 | 0.0 | 686 | 686 | 686.0 | 62.4 |
| SYM-2P v1 | 0 | 0 | 0.0 | 2719 | 2719 | 2719.0 | 247.2 |
| SYM-2P v2 session + handshake (PR #6) (PR #6 dense pilot numbers) | 213 | 213 | 21.3 | 1202 | 1415 | 1223.3 | 128.6 |
| SYM-3 delta | 524 | 198 | 19.8 | 349 | 873 | 368.8 | 79.4 |
| SYM-3 refs | 524 | 198 | 19.8 | 241 | 765 | 260.8 | 69.5 |
| SYM-3 positional | 524 | 199 | 19.9 | 256 | 780 | 275.9 | 70.9 |
| SYM-3 omit | 524 | 198 | 19.8 | 357 | 881 | 376.8 | 80.1 |
| SYM-3 combined | 524 | 198 | 19.8 | 334 | 858 | 353.8 | 78.0 |
| SYM-3 adaptive | 524 | 198 | 19.8 | 241 | 765 | 260.8 | 69.5 |

† Cached setup assumption (10% of min setup tokens), not API-measured.

### Break-even vs compact JSON / lossless English (setup min, o200k)

| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |
| --- | ---: | ---: |
| adaptive | 5 | 5 |
| combined | 7 | 7 |
| delta | 7 | 7 |
| omit | 7 | 7 |
| positional | 6 | 6 |
| refs | 5 | 5 |

## lifecycle_40 (40 messages)

| Format | setup full | setup min | setup cached† | messages | total (full setup) | total (cached setup)† | amortized full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact JSON | 0 | 0 | 0.0 | 5343 | 5343 | 5343.0 | 133.6 |
| pretty JSON | 0 | 0 | 0.0 | 6516 | 6516 | 6516.0 | 162.9 |
| English (lossy summary) | 0 | 0 | 0.0 | 2283 | 2283 | 2283.0 | 57.1 |
| English (lossless) | 0 | 0 | 0.0 | 5242 | 5242 | 5242.0 | 131.1 |
| SYM-2P v1 | 0 | 0 | 0.0 | 12925 | 12925 | 12925.0 | 323.1 |
| SYM-3 delta | 524 | 198 | 19.8 | 3356 | 3880 | 3375.8 | 97.0 |
| SYM-3 refs | 524 | 198 | 19.8 | 1463 | 1987 | 1482.8 | 49.7 |
| SYM-3 positional | 524 | 199 | 19.9 | 2507 | 3031 | 2526.9 | 75.8 |
| SYM-3 omit | 524 | 198 | 19.8 | 3364 | 3888 | 3383.8 | 97.2 |
| SYM-3 combined | 524 | 198 | 19.8 | 2312 | 2836 | 2331.8 | 70.9 |
| SYM-3 adaptive | 524 | 198 | 19.8 | 1463 | 1987 | 1482.8 | 49.7 |

† Cached setup assumption (10% of min setup tokens), not API-measured.

### Break-even vs compact JSON / lossless English (setup min, o200k)

| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |
| --- | ---: | ---: |
| adaptive | 3 | 3 |
| combined | 3 | 3 |
| delta | 4 | 5 |
| omit | 5 | 5 |
| positional | 3 | 3 |
| refs | 3 | 3 |

## lifecycle_200 (synthetic, 5× lifecycle_40)

Baselines: compact JSON **27363** tokens; English (lossless) **26595** tokens (messages only).

| Encoder | setup min | messages | total (full) | total (cached)† | < compact? (full/cached) | < English lossless? (full/cached) |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| adaptive | 198 | 7373 | 7571 | 7392.8 | True/True | True/True |
| combined | 198 | 11619 | 11817 | 11638.8 | True/True | True/True |
| delta | 198 | 17324 | 17522 | 17343.8 | True/True | True/True |
| omit | 198 | 17364 | 17562 | 17383.8 | True/True | True/True |
| positional | 199 | 13079 | 13278 | 13098.9 | True/True | True/True |
| refs | 198 | 7374 | 7572 | 7393.8 | True/True | True/True |

## Verdict (honest accounting, o200k_base)

SYM-3 wire messages are smaller than compact JSON, but a receiver still needs lexicon + schema context (hundreds of tokens once per session, less when trimmed to the transcript). On **lifecycle_11**, minimal setup plus messages **does not** beat compact JSON or lossless English at 11 messages; break-even counts in the tables above show how many messages are needed when average per-message rates from that transcript are extrapolated linearly. **refs** / **adaptive** pull ahead on long transcripts with repeated bodies (see lifecycle_40/200), especially when the cached-prefix pricing assumption applies. English (lossy summary) is **not** comparable to canonical payloads; use the lossless English row.

