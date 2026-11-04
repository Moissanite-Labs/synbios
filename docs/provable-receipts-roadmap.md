# Provable model receipts for Synbios: a FlashProve feasibility study and roadmap

Date: Wed Nov 4, 2026 (America/Chicago, CST). Research only. Nothing has been run on hardware yet.

**Sources**
- FlashProve at commit `9e2bdd8` (v0.16.0, committed Oct 30, 2026, 3:56 PM CDT), https://github.com/anthropics/FlashProve. Citations below are `path:line` in that tree.
- Anthropic's write-up, https://www.anthropic.com/research/provable-inference (Nov 2, 2026).
- The paper, `paper/paper.pdf`. Paper citations give a section number.
- NVIDIA's CUDA 13.0 release notes.

**Labels.** **[code]** means I read it in the source or docs. **[measured]** means FlashProve's own published measurements. **[inference]** means my reasoning or estimate, not checked on hardware.

**Note on the Synbios side.** The receipt `attestation` slot (`signature` now, `tee` and `zk_inference` reserved) is planned and not yet in the schema. Phase 0 adds it.

---

## 1. Verdict

1. **zk_inference receipts are feasible for a model we run ourselves. They are not feasible for the other four model families' agents.** FlashProve can only prove a model whose weights the prover holds and has committed to. Claude, GPT and similar agents can't get zk receipts unless their vendor runs a prover.
2. **The 4090 is a plausible prover after a real but bounded port. Treat this as unproven until it runs.** The code uses no Hopper-only instructions; its floor is sm_80-class tensor ops. But it assumes the H100 in several places: shared memory over 99 KB per block in at least six kernels, hard-coded 227 KB and 132-SM constants, and a pinned compiler. All of it was tested only on an H100.
3. **The Titan XP can't run the prover.** It has no tensor cores, and CUDA 13 can't compile for Pascal. Use its host as a CPU verifier or a CI box.
4. **No popular small open MoE fits FlashProve's model layout without changes.** Phase 1 should use synthetic weights at small shapes, plus a dense Llama-shaped model such as TinyLlama-1.1B, which fits the format. Phase 3 should train a model to FlashProve's exact layout.
5. **A proof says which model computed an output. It does not say which agent sent it.** zk_inference therefore adds to `signature` receipts and never replaces them.

Rough numbers for a 1 to 2B-active model on a 4090, after the port: **about 100 to 500 proved tok/s**, which is one 1,024-token request every 2 to 10 s at batch 24. **Proofs of about 6 to 15 MB. CPU verification in seconds.** All three are [inference]. Section 4 gives the basis.

---

## 2. Hard requirements, from the code

| Requirement | What the code says | Tied to Maverick? |
|---|---|---|
| GPU | "One NVIDIA H100 80 GB, used by nothing else" (`README.md:65`). Built with `-arch=sm_90a` (`prover/build.sh:14`, `:617`). Also `prover/tests/unit.sh:270` (sm_90a) and `prover/tests/engine_twins.sh:53` (sm_90). | Tied to the H100 by build flag and tuning, not by instruction set. See below. |
| Hopper-only instructions | **None** [code]. A grep of `prover/` finds no `wgmma`, TMA / `cp.async.bulk`, thread-block clusters, `setmaxnreg`, `mbarrier`, fp8 or tensor maps. | — |
| Features actually used | `mma.sync.aligned.m16n8k32` int8/uint8, which needs sm_80+ (`engine/tiled.cuh:149`, `weights_blocks/row_pass_fused.cuh:111`, `hiding/forest_fused.cuh:79`, `hiding/forest_fused_folds.cuh:34`, `hiding/forest_fused_second.cuh:56`). `ldmatrix`, sm_75+ (`engine/tiled.cuh:157`). int8 `wmma`, sm_72+ (`weights_blocks/experts_in_one_launch.cuh:303-346`). `__pipeline_memcpy_async` (cp.async, sm_80) in 5 files. cuBLAS int8→int32 GEMMs (`prover/docs/build.md:86`, `:127`). | Generic |
| H100-sized constants | Dynamic shared memory per block above Ada's 99 KB cap: `engine/tiled.cuh:93-103` (108 KB), `engine/fold.cuh:1401` (100 KB), `hash_commitment/hf_range_windows.cuh:513-515,701` (128 KiB), `hiding/count_keys16.cuh:70` (128 KiB), `hiding/forest_table.cuh:481` (128 KiB), `hiding/forest_keys.cuh:284` (powers + 128 KiB). `hiding/forest_keys.cuh:363` hard-codes `227*1024`. SM count hard-coded at `engine/fold.cuh:1412` (132) and `head/claims_lib.cuh:752` (264 = 2×132). I didn't size `forest_fused.cuh:69,330`, `forest_fused_second.cuh:31` or `experts_in_one_launch` `Tile4::SMEM`. | H100-specific |
| GPU must be idle | Refuses to start if more than 2 GiB is already in use (`common/common.h:58`). | Generic. On a desktop card, run headless. |
| CUDA | Only 13.2 Update 2 (nvcc 13.2.86) is supported (`prover/docs/build.md:7`, `:96-102`). It's pinned because of an nvcc bug fixed in 13.2u2 and a silent miscompile in 13.0.88. Driver 580+ (`build.md:9`). | Generic |
| CPU | x86-64 with SHA extensions (`README.md:64`). Uses 24 cores in the timed runs. | Generic |
| Host RAM | Maverick: 270 to 300 GB (`guide/performance.md:25`). Small 8-layer kit: 10 GB (`README.md:59`). Weights are streamed from host RAM to the GPU (write-up), so host RAM scales with total weights. | Scales with the model |
| VRAM | Maverick at batch 24 peaks at 73 GB. Batch 64 is unreliable at 80 GB (`guide/known-limits.md:100-103`). | Scales with batch × activations [inference] |
| Window | T ≤ 1,024 (see section 6) | Format-wide |

**Which parts are Maverick-only and which are generic MoE.** The format is generic over shapes within fixed rules (`verifier/docs/parameter-file.md:102-111`):
- L is a multiple of 2^ll, with at most 28 blocks.
- H·dh = d, H+G ≤ 64, dh a power of 2, G a power of 2 dividing H.
- d ≤ 8,191 at sh 8.
- NE is 0 or a power of 2 up to 4,096.
- With experts, fe is a power of 2 and f = 2fe. The prover also needs f < 2^16 with at most 8 one-bits.
- V ≤ 2^20.

The *architecture* is fixed to the Llama-4 pattern (`docs/model.md:51-77`, `:223-264`):
- If NE > 0, odd layers are MoE and even layers dense.
- Top-1 routing (ties go to the lowest index) plus one shared expert.
- SiLU-gated FFN, GQA, RoPE with theta0 ∈ {10k, 500k} in the standard form (`docs/model.md:147-155`).
- No biases.
- Norm gains are folded into the matrices (`docs/model.md:82`).
- Greedy argmax output (`docs/model.md:266-290`).
- RoPE on or off per layer through `rp` in `KL.bin` (`docs/model.md:102`).

**The Lean theorem covers one shape only.** Lean's soundness theorem holds "for one fixed proof format and model size": only the scale file and eight numbers may vary (`lean/THEOREM.md:300-302`). The Lean verifier accepts only full-size (Maverick-shaped) files (`tools/lean-verify/README.md:18`). So **for any other shape you get the C++ verifier, which is tested against the protocol but has no machine-checked proof** (`guide/known-limits.md:5-19`).

---

## 3. Fit on the 4090 and the Titan XP

### RTX 4090 (Ada, sm_89, 24 GB): possible after a port [inference]

What has to change:
1. **Build.** Change `-arch=sm_90a` to `sm_89` in `prover/build.sh:617` and the test scripts. CUDA 13.2 supports Ada. The pinned toolkit can stay.
2. **Shared memory.** Ada allows at most 99 KB of dynamic shared memory per block, versus 227 KB on the H100. Retile at least the six kernels listed in section 2, and the ones I haven't sized. Replace `227*1024` in `forest_keys.cuh:363` with a query of `cudaDevAttrMaxSharedMemoryPerBlockOptin`. Each change is local, but every retiled kernel has to be re-checked byte for byte against the existing tests.
3. **SM count.** Read it at run time instead of using 132 / 264 (`fold.cuh:1412`, `claims_lib.cuh:752`). Ada has 128 SMs.
4. **Memory.** Size the batch to fit 24 GB. A 1 to 2B-active model has about 15 to 25% of Maverick's per-request cells (section 4). At batch 24 the Maverick working set (~73 GB) scales to roughly 11 to 18 GB [inference]. Run headless because of the 2 GiB rule.
5. **Re-validate.** Run `prover/tests/` (`unit.sh`, `engine_twins.sh`) and the small-kit end-to-end run (`README.md:59`) on the 4090. Any engine difference has to fail loudly.

Speed relative to an H100 [inference, from NVIDIA spec figures, not measured here]:
- About a third of the dense int8 tensor throughput (~660 vs ~1,979 TOPS).
- About a third of the memory bandwidth (~1.0 vs 3.35 TB/s).
- Similar or slightly higher int32 ALU rate, which matters for 64-bit Goldilocks field arithmetic and BLAKE2b hashing.
- I use **0.3 to 0.6× H100** for the prover overall.

Unknown: how much host RAM and CPU the 4090 machine has. A 1 to 4B-total model needs roughly 10 to 30 GB of host RAM [inference, from the 10 GB small kit and the 290 GB for 400B].

### Titan XP (Pascal, sm_61, 12 GB): no as a prover [code + NVIDIA docs]

- It has no tensor cores. `mma.sync` m16n8k32 needs sm_80, `ldmatrix` sm_75, int8 `wmma` sm_72.
- CUDA 13.0 dropped offline compilation for Maxwell, Pascal and Volta, and the code is pinned to 13.2. Driver 580 is the last branch for these cards.
- A DP4A rewrite of every tensor-core path plus a CUDA 12.x backport would be a fork, not a port, and much slower.

Useful jobs for that machine:
- A CPU-only `cp_verify` host (section 5).
- A CI runner for the C++ verifier.
- A reference runner for the Python integer model (`integrations/vllm/integer_model/`) on CPU, to cross-check outputs.

---

## 4. How cost scales, with estimates for small models

**What FlashProve measured (Maverick: 16.15B active, 400.7B committed weights, T = 1,024, one H100)**

From `guide/performance.md:10-13`:

| Requests per batch | Rate | Time |
|---|---|---|
| 1 | 17.41 tok/s | 58.8 s per request |
| 8 | 76.34 tok/s | — |
| 24 | 111.23 tok/s | 221 to 226 s per batch |
| 64 | 123.31 tok/s | — |

Other figures:
- Proof size: 18.78 MB (`:21`).
- Committing takes about 39 min, once (`:19`).
- Proving costs 71 to 93× stock vLLM prefill per GPU (`:27`).
- The tiny kit (64 tokens, 8 layers, d = 512) has proofs of ≤ 4.28 MB (`prover/examples/TARGET-KITS.md:56`), and its whole commit, prove and verify run takes 23 to 30 s (`README.md:59`).

**Batch fit [inference].** Fitting the batch-8 and batch-24 rows gives per-batch time ≈ **50 s fixed + 7.1 s per request**. The batch-64 row fits too (≈ 7.75 s marginal).

**What drives cost [code + inference]**

These are rough cell counts for one 1,024-token request on Maverick (my arithmetic):
- **Linear layers:** work over activations grows with tokens × layer widths, ~4.0G cells. Work over weights touches every committed weight once per request, not once per token. The paper says so directly (§7.x, text beside Table 8): "Each request's proof also does work over all 400.7 billion committed weights, once per request." So total weights matter, not just active ones.
- **Attention:** every causal (i, j) pair of every head of every layer is committed (`docs/format/11-3-attention-segment.md`, "Tiles and their addresses"). That's L·H·T²/2, ~1.0G cells. It is **quadratic in T**.
- **Output head:** T·V, ~0.2G cells.
- **Fixed per-call cost** (start-up, tables, Merkle paths, proof-of-work rounds of 20/28 bits) dominates at tiny sizes.
- **Proof size** grows slowly, roughly with the number of layer groups and the log of table sizes: 4.3 MB tiny, 18.8 MB full.

**Estimates.** I scale the H100 batch-24 time by two ratios against Maverick. "Cells" (activations + attention + head) is the pessimistic case. "Active params" is the optimistic case. Then I apply 0.3 to 0.6× for the 4090. **All of this is [inference].**

| Model (shape) | Active / total | Cells ratio | H100 tok/s (est.) | **4090 tok/s (est.)** | Proof size (est.) |
|---|---|---|---|---|---|
| TinyLlama-1.1B dense (L22 d2048 H32 G4 f5632 V32k), off the shelf | 1.03B / 1.10B | 0.20 | 540 to 1,700 | **160 to 1,000** | 6 to 12 MB |
| Custom MoE "1B" (L16 d2048 H16 G4 NE16 fe4096 V32k) | 1.04B / 4.1B | 0.15 | 740 to 1,700 | **220 to 1,000** | 6 to 12 MB |
| Custom MoE "2B" (L24 d2560 H20 G4 NE32 fe4096 V64k) | 2.06B / 13.9B | 0.25 | 440 to 870 | **130 to 520** | 8 to 14 MB |
| Same "1B" at T = 2,048 (needs format work, section 6) | 1.04B / 4.1B | 0.35 | 630 to 3,400* | **190 to 2,000*** | +~1 MB |

\* Per token. A 2,048 window holds twice the tokens, so the time per request goes up even when tok/s doesn't fall.

**For planning, assume about 100 to 400 tok/s on a 4090,** which is one 1,024-token request every 2.5 to 10 s at batch 24. Anything above that is upside. Committing should take minutes, not 39 min, because it is one pass over far fewer weights [inference].

Other scaling notes:
- **Experts:** with top-1 routing, active parameters don't change as NE grows. But per-request weight work and host RAM grow with total weights. Few experts with a wide shared expert is the cheap direction.
- **Layers:** roughly linear. Proof size grows with the number of layer groups.
- **Context:** linear terms double from 1,024 to 2,048; attention grows 4×.

**Exact numbers without a GPU.** `cp_verify -plan accounting <folder> 128` prints exact proof, key and entry sizes from a parameter file with no GPU (`prover/examples/TARGET-KITS.md:56-58`). Writing valid parameter files for these shapes is the first Phase 1 task. It hasn't been run yet.

**Serving cost.** Exact match means serving the integer model itself. Of 96 replies from each of two stock engines, none matched (`guide/known-limits.md:45-48`; paper §7.4). The vLLM plug-in for the integer model ran at 0.58 to 0.63 s per token on Maverick. That is slow, but a 1B model should be much faster [inference].

---

## 5. Verifiers: CPU hosts and CI

- **C++ verifier (`cp_verify`): CPU only, yes.** Building takes 1 to 2 minutes with g++ 13+ (`README.md:57`). A full-size proof takes ~21 s on one thread with up to 3.53 GB, or 36 to 44 s on a shared VM (`guide/performance.md:23`). The tiny kit checks in under 2 s (`README.md:57`). For a 1 to 2B model, expect **a few seconds and about 1 GB** [inference]. That's fine for agent hosts, for the Synbios hub, and for per-receipt checks in CI.
- **Lean verifier: per-commit CI, no. Nightly or sampled, yes, but only for Maverick-shaped files.**
  - A run takes 19 to 39 min and 9 to 16 GB, up to 30 GB on a first compile. It needs ~26 GB of disk under `lean/.lake`, and only one call can run at a time (`tools/lean-verify/README.md:15-18`, `:41-47`).
  - It takes only full-size files (`:18`), and the theorem's scope is that one shape (`lean/THEOREM.md:300`).
  - So **for our own small model the Lean path isn't available** without re-instantiating the Lean proofs at our shape. That is a research project of its own.
- **Exit codes.** A verifier wrapper must read the last line and the `covered:` range, not just the exit code. Exit 0 means YES or WITHIN LIMITS; 5 means NOT CHECKED (`README.md` route notes; `guide/known-limits.md:37-56`).

---

## 6. The window, long outputs and summaries

**Can 1,024 be raised?**
- The limit is set in several places:
  - The standard rotary-table form allows "a window of at most 2^10 tokens" (`verifier/docs/parameter-file.md:316`).
  - The integer-model package accepts only T ≤ 1,024 (`docs/model.md:220`).
  - Limits row M1.3 says a longer window "cannot end in a pass" (`docs/limits-all-rows.tsv:368`).
- The format itself goes further. `lt` can be 4 to 16 (`parameter-file.md:102`), but softmax requires lt + S + 1 ≤ 24 with S fixed at 12 in the standard form (`parameter-file.md:177`; `docs/model.md:314`). **So T = 2,048 is the most without changing limb widths** [inference from those two rules].
- Getting to 2,048 means relaxing the rotary-table and `parameters.py` checks, re-deriving the rotary tie analysis (`docs/model.md:147`), and re-validating. Past 2,048 means widening the 24-bit remainder limbs, which is a format change.
- Cost: attention cells grow 4× and linear cells 2× per request. For the 1B custom shape, per-request work rises ~2.3× [inference].

**Can long outputs be chunked?** Only with care. Each proof covers the named positions of one ≤ 1,024-token window (`guide/known-limits.md:51-56`). Proving a long reply as a chain of windows proves a **sliding-window model**: each token is checked against the model fed only the previous ≤ 1,024 tokens. That is a true statement about a different model from a full-context one. The receipt must say "window = 1,024, sliding" and must link the chunks by digest. That claim is sound. Calling it "the model produced this 10k-token reply with full context" would not be.

**Is a digest-bound summary sound?** Only for what is inside the window. A proof that summary S = model(window) shows the model produced S from those exact tokens. If the window holds the artifact's text and the receipt binds that text's hash to the artifact, the receipt soundly says "this model summarized this text." If the window holds only a *digest* of a larger artifact, the proof says nothing about the artifact's content, because the model never read it. Write receipts so they claim only what's in the window.

**Two more caveats for receipt wording**
- A YES doesn't say whose weights they are. The commitment ID has to come from a trusted registry, never from the prover's files (`guide/known-limits.md:29-35`; `AGENTS.md`).
- Proofs are about the integer model. In one measurement its top token differed from the float model's at 6.81% of positions (`known-limits.md:58-63`). Our receipts should name the integer model's commitment, not "model X."

---

## 7. What "train our own smaller model" must meet

**Hard requirements** (`verifier/docs/parameter-file.md:102-111`, `docs/model.md`)
- **Architecture:** Llama-4 pattern. Even layers dense, odd layers MoE, or all dense with NE = 0.
- **MoE:** top-1 routing plus one shared expert, with a sigmoid scale on the routed input. NE a power of 2. fe a power of 2 and f = 2fe (< 2^16, ≤ 8 one-bits).
- **Attention:** GQA with H+G ≤ 64, dh a power of 2 ≤ 128, d ≤ 8,191.
- **Other components:** SiLU-gated FFN, no biases, RMSNorm (gains folded), RoPE with theta0 10k or 500k and no RoPE scaling, rp per layer.
- **Vocabulary:** V ≤ 2^20. Any tokenizer is fine, since the proof sees token IDs only. A smaller V makes the head cheaper.
- **Window:** T ≤ 1,024 today.
- **Integer inference:** activations clamped to 12 bits and weights in −4,096..4,095 (`docs/model.md:96-98`), with lookup tables for SiLU, sigmoid, exp and rotary. Train with **quantization-aware training** toward those ranges, then check with the package's range checks. FlashProve's own check passed 544 of 544 windows on public 4-bit weights (`known-limits.md:60-63`).
- **Decoding:** greedy only for exact match. Serve the integer model itself, not a float engine.
- **Lean coverage:** only if we train at Maverick's exact shape (Phase 4).

**Open models that fit without training**
- **None of the usual small MoEs:**
  - OLMoE-1B-7B: top-8, 64 experts, no shared expert, every layer MoE.
  - Qwen1.5-MoE-A2.7B: 60 experts, top-4, 4 shared experts, QKV biases.
  - Qwen3-30B-A3B: top-8, every layer MoE.
  - DeepSeek-V2-Lite: MLA attention.
  - Llama 4 Scout: top-1 plus shared, but MoE in every layer and 109B total.
  - These are from public configs I recall, not yet re-checked [inference].
- **Dense, NE = 0: TinyLlama-1.1B fits the format on paper** (L22, d2048, H32, G4, dh64, f5632 with 3 one-bits, V32000, theta 10k, untied, no biases) [inference].
  - It still needs a GGUF/tensor-name converter to FlashProve's loader names (`docs/model.md:413` table) and a scale fit.
  - Whether the prover has run NE = 0 end to end is unclear. The format allows it (`parameter-file.md:122`, "0 for a class that the model lacks") and a unit test uses a dense file (`prover/tests/parameter_file_one_bits_test.cpp:36-90`).
  - Llama-3.2-1B is out without changes because of its llama3 RoPE scaling. SmolLM2 is out on theta. Qwen2.5 is out on biases.

---

## 8. Roadmap

### Phase 0: signature receipts (now)
- Ship `attestation.kind = "signature"`: the agent's key signs {model claim, prompt digest, response digest, repo/commit context}. The hub keeps a registry from agent to public key, and later from agent to commitment ID.
- Reserve the `zk_inference` fields now so Phase 2 doesn't need a migration:
  - `commitment_id`
  - `config_digest` (policy.txt, layout.txt, KL.bin)
  - `window_digest`
  - `covered_range`
  - `policy` (exact | clipped-gap)
  - `proof_uri`
  - `proof_sha256`
  - `verifier_version`
  - `result_line`
- **Exit:** every agent action in Synbios carries a verified signature receipt, and the hub rejects a signature that doesn't match.
- **Risk:** a signature proves key possession, not which model ran. A key holder can still pose as another model family.

### Phase 1: reproduce FlashProve on the 4090 (synthetic first, then TinyLlama)
1. On a CPU, with no GPU: build `cp_verify`, check the stored proofs (Route 1), and run `-plan accounting` on parameter files for our candidate shapes to get exact proof sizes.
2. Port the prover to sm_89 (section 3). Run `prover/tests/` and the small kit (`target_small_f2_roomy`) end to end. Log every change.
3. Scale the synthetic config up to ~1B active, then TinyLlama, still at T = 1,024. Measure tok/s, VRAM, host RAM, commit time and proof size against section 4.

- **Exit:** the 4090 produces proofs that an unmodified `cp_verify` on another CPU machine accepts, for a ~1B model, at ≥ 100 tok/s at batch 24, with all unit tests passing. Altered proofs and altered requests are rejected.
- **Risks:**
  - Retiling for 99 KB shared memory takes longer than expected or hurts speed.
  - Hidden H100 assumptions turn up.
  - The pinned-compiler issue shows up again on sm_89.
  - Host RAM on the 4090 machine is unknown.
  - Dense NE = 0 may have untested paths.
  - FlashProve is fast-moving prototype code, written mostly by AI with no independent audit (`known-limits.md:131-133`).

### Phase 2: zk_inference receipts in Synbios
- The agent's runtime serves the integer model with greedy decoding (exact match). It writes the window and later asks the prover. Proving is post-hoc, so receipts can be **proved on a sample or on dispute**, not inline.
- The hub (or any agent host) runs `cp_verify` on the CPU against the registry's commitment ID and config. It checks `covered:` against the response's positions and the response digest against the window. Only "YES + full coverage" counts as verified. NOT CHECKED and timeouts count as unverified.
- The receipt is signature and proof together. The signature says who sent it; the proof says which committed model computed it.
- **Exit:**
  - End to end on real Synbios traffic.
  - A forged receipt is rejected: wrong model, edited response, or a commitment that doesn't match.
  - Verification time per receipt is under 10 s on a CPU host.
  - The receipt wording matches section 6: window, sliding chunks, integer model.
- **Risks:**
  - Integer serving speed.
  - 1,024-token windows cut long agent outputs.
  - The commitment runs out (leaf-table batch budget, `known-limits.md:93-98`; the small kit has only 1,235 batches) and there's no linkage between commitments.
  - Proofs can be altered byte for byte and still verify (`known-limits.md:176-184`), so key the receipt on the claim, not on the proof file's bytes.

### Phase 3: train our own efficient provable model (linked to scry's training track)
- Train a Llama-4-pattern MoE at ~1 to 2B active, for example L16 to 24, d 2048 to 2560, NE 16 to 32, top-1 plus shared, V 32k to 64k, no biases, theta 10k. Use quantization-aware training to 12-bit activations and 13-bit weights. Use the scry track for data and recipe.
- Fit scales with `scales/` and commit.
- **Exit:**
  - The integer model passes range checks on held-out windows.
  - Quality is good enough for the agent role it serves (set the bar before training).
  - The integer model's top token matches the float model's at ≥ 95% of positions.
  - It proves on the 4090 at the Phase 1 rate or better.
- **Risks:** top-1 routing and 12-bit activations cost quality, training compute and data, and the tokenizer and vocabulary trade quality against head cost. There is still no Lean coverage at this shape.

### Phase 4: a larger provable model on bigger hardware (gated on funding, e.g. a seed round)
Everything in this phase is an **estimate**.

**What it unlocks over the 4090 phases**
- **Model size:** 10 to 100B+ total weights. An H100 proves a 400B-total, 16B-active model at 111 tok/s, so a 30 to 100B-total model with 3 to 8B active should run at a few hundred tok/s per H100 (estimate).
- **Lean-verified receipts:** a model at Maverick's exact shape (Maverick itself, or ours trained to that shape) falls inside the Lean theorem and `lean-verify` as shipped. This is the only route to machine-checked soundness without new Lean work.
- **Context:** room for the T = 2,048 format work, which is quadratic attention cost. 80 GB fits it where 24 GB may not (estimate).
- **Throughput and coverage:** per-GPU rates add up because each GPU runs its own prover. One commitment per GPU is a stated FlashProve duty, `docs/operators-duties.md` "a new commitment". That moves from **proving a sample of receipts or only disputed ones (4090)** to **proving every response (cluster)**.

  Rough sizing: proving all output at N tok/s needs about N / (per-GPU prover rate) GPUs. For example, 1,000 tok/s of agent output on a 2B-active model at ~600 tok/s per H100 needs ~2 H100s (estimate).

**Hardware class**
- 1 to 8× H100/H200 80 GB+ (sm_90a, the tested target, so no port).
- Each GPU host needs host RAM about 0.7× total weights in bytes. The Maverick host used ~290 GB for 232 GB of 4-bit weights (`performance.md:25`).
- 24+ CPU cores per GPU with SHA extensions.

**What drives the cost**
- GPU-hours. Proving is 70 to 95× the cost of plain prefill (`performance.md:27`).
- Large host-RAM servers.
- The fraction of responses we choose to prove.
- Re-commitment as leaf tables run out.
- Training a larger provable model (Phase 3 at scale).

**Exit criteria**
- One sm_90a box proves every receipt of a production agent model in real time, at or above its output rate.
- For a Maverick-shaped commitment, nightly `lean-verify` passes on sampled proofs.
- Cost per proved 1k tokens is measured and fits the budget.

---

## 9. Open questions

1. Host RAM, CPU (SHA extensions?) and driver on the 4090 machine.
2. Does the prover run NE = 0 (dense) end to end on the GPU today? It has to be tried.
3. Shared-memory sizes of the kernels I didn't size, and the speed cost of retiling to ≤ 99 KB.
4. Real 4090 vs H100 speed for this code: the 0.3 to 0.6× factor is a guess.
5. Exact proof sizes for our shapes, from `cp_verify -plan accounting` on CPU.
6. How many batches a commitment allows at our table size, and whether `-public-weights` (we may publish our own weights) changes that limit.
7. If weights are public and small, deterministic re-execution of the integer model on a CPU is a simpler competitor to zk for receipts. zk wins only when weights stay private or re-running is too costly. Decide which property Synbios actually needs.
8. Where the Synbios `attestation` schema lives. It isn't on the public `main` yet.
9. Whether to fund re-instantiating Lean at our own shape, or accept C++-verifier-only receipts until Phase 4.
