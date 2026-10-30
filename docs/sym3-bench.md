# SYM-3 benchmark

## lifecycle_11 (11 messages)

| Format | setup (o200k) | messages (o200k) | total | amortized/msg |
| --- | ---: | ---: | ---: | ---: |
| plain JSON | 0 | 682 | 682 | 62.0 |
| minified JSON | 0 | 682 | 682 | 62.0 |
| English prose | 0 | 478 | 478 | 43.5 |
| SYM-2P v1 | 0 | 2719 | 2719 | 247.2 |
| SYM-2P v2 session (steady) (from PR #6 dense pilot; handshake amortized in total) | 213 | 1202 | 1415 | 128.6 |
| SYM-3 delta | 5 | 347 | 352 | 32.0 |
| SYM-3 refs | 5 | 241 | 246 | 22.4 |
| SYM-3 positional | 5 | 256 | 261 | 23.7 |
| SYM-3 omit | 5 | 356 | 361 | 32.8 |
| SYM-3 combined | 5 | 334 | 339 | 30.8 |
| SYM-3 adaptive | 5 | 241 | 246 | 22.4 |

<details><summary>cl100k / open tokenizer totals</summary>

### cl100k_base

| Format | setup (cl100k_base) | messages (cl100k_base) | total | amortized/msg |
| --- | ---: | ---: | ---: | ---: |
| plain JSON | 0 | 680 | 680 | 61.8 |
| minified JSON | 0 | 680 | 680 | 61.8 |
| English prose | 0 | 479 | 479 | 43.5 |
| SYM-2P v1 | 0 | 2689 | 2689 | 244.5 |
| SYM-2P v2 session (steady) | 0 | 0 | 0 | 0.0 |
| SYM-3 delta | 5 | 351 | 356 | 32.4 |
| SYM-3 refs | 5 | 243 | 248 | 22.5 |
| SYM-3 positional | 5 | 258 | 263 | 23.9 |
| SYM-3 omit | 5 | 359 | 364 | 33.1 |
| SYM-3 combined | 5 | 336 | 341 | 31.0 |
| SYM-3 adaptive | 5 | 243 | 248 | 22.5 |

</details>

## lifecycle_40 (40 messages)

| Format | setup (o200k) | messages (o200k) | total | amortized/msg |
| --- | ---: | ---: | ---: | ---: |
| plain JSON | 0 | 5343 | 5343 | 133.6 |
| minified JSON | 0 | 5343 | 5343 | 133.6 |
| English prose | 0 | 2283 | 2283 | 57.1 |
| SYM-2P v1 | 0 | 12925 | 12925 | 323.1 |
| SYM-3 delta | 5 | 3353 | 3358 | 84.0 |
| SYM-3 refs | 5 | 1463 | 1468 | 36.7 |
| SYM-3 positional | 5 | 2507 | 2512 | 62.8 |
| SYM-3 omit | 5 | 3362 | 3367 | 84.2 |
| SYM-3 combined | 5 | 2312 | 2317 | 57.9 |
| SYM-3 adaptive | 5 | 1463 | 1468 | 36.7 |

<details><summary>cl100k / open tokenizer totals</summary>

### cl100k_base

| Format | setup (cl100k_base) | messages (cl100k_base) | total | amortized/msg |
| --- | ---: | ---: | ---: | ---: |
| plain JSON | 0 | 5404 | 5404 | 135.1 |
| minified JSON | 0 | 5404 | 5404 | 135.1 |
| English prose | 0 | 2336 | 2336 | 58.4 |
| SYM-2P v1 | 0 | 12895 | 12895 | 322.4 |
| SYM-3 delta | 5 | 3423 | 3428 | 85.7 |
| SYM-3 refs | 5 | 1478 | 1483 | 37.1 |
| SYM-3 positional | 5 | 2574 | 2579 | 64.5 |
| SYM-3 omit | 5 | 3431 | 3436 | 85.9 |
| SYM-3 combined | 5 | 2327 | 2332 | 58.3 |
| SYM-3 adaptive | 5 | 1478 | 1483 | 37.1 |

</details>


**Verdict (o200k_base):** On the 11-command lifecycle, SYM-3 `refs` and `adaptive` total **246 tokens** (22.4/msg amortized with setup) vs **682** plain JSON and **478** English prose — roughly **2.8×** and **1.9×** savings respectively; they also beat SYM-2P v1 (**2719**) and v2 session+handshake (**1415**). On the 40-message transcript, `refs`/`adaptive` drop to **1468** total vs **5343** JSON, where repeated bodies and digests dedupe through the content store.

