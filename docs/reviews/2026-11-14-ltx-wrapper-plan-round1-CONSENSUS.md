# CONSENSUS REPORT — LTX wrapper + WAN stills/I2V upgrade plan (round 1)

**Date:** 2026-11-14
**Reviewers:** GPT/Hermes `gpt-6.1-sol-900k` (hermes-consensus-bridge, run 20261114T132812.731698Z-38e3a96a0b) + Claude Opus 5.5 (`claude-opus-5-5`, xhigh, 33 turns, read-only + live peer SSH)
**Source plan:** `/home/jose-a-pichardo/Wan2.2/docs/2026-11-14-ltx-wrapper-implementation-plan.md`
**Project:** Wan2.2 fork (peer build for Locksmith APP ads HG-2) · **Branch:** main · **HEAD:** 4b791db · **Origin delta:** 3 ahead / 0 behind (local docs commits; peer checkout diverged at 3a4b80b — reconciliation is Jose's)
**Rounds:** 1 · **Completion barrier:** both seats returned EXIT=0; full outputs read and reconciled before this report.

---

## 1. Executive verdict

**REVISE BEFORE EXECUTION — both seats, independently.** Architecture (D1 shared ComfyUI, D2 Q3, D3 LTX+WAN, D4 wrapper-owned mapping, frozen engine) is endorsed by both. Eight consolidated blockers (C1–C8) are bounded plan/design amendments; none requires an engine change, a second generator, or new infrastructure. No credible disagreement between the seats — the blocker sets are complementary, so no tie-breaker is needed.

## 2. Live-state verification performed

- **GPT seat:** reproduced the bridge pins (branch/HEAD/fingerprint/input hash) before and after review; exercised the actual adapter function bodies in Node with an injected transport (submit/poll outcome table incl. cancelled→poll_failure); parsed the Q3 graph (31 nodes, 41 links, no dangling refs); executed the captured WAN builder via AST (9 T2V nodes, cfg 5.0 hardcoded, no image path); **reproduced the WAN timeout state reversal offline** with the captured `_process_loop` method (failed→completed after late executor return).
- **Opus seat:** verified the engine copies byte-identical to the Locksmith tree; read `local-config.mjs`, `jobs.mjs` poll/retry budgets, `core/download.mjs` (250 MiB + ftyp); **live peer SSH:** wan configs (`ti2v-5B` SUPPORTED_SIZES), WanVideoWrapper `nodes.py`/`nodes_sampler.py`/`model.py`, the shipped 5B I2V example workflow, ComfyUI `nodes_lt.py` (32-px grid, center-crop behavior), RUNBOOK, live `calibration.json` (3.2486e-7 s/unit → ≥1472 s floor for the HG-2 clip), ffprobe of all 19 prior WAN outputs (all 704×1280×17), still dimensions (941×1672 portrait), venv inventory (pytest ABSENT; httpx/fastapi/pydantic present), `/queue` empty, **GPU1 "Unknown Error"** (only GPU0 enumerated).
- **Orchestrator spot-checks (this session, read-only SSH, 2026-11-14):** confirmed `ti2v-5B: ('704*1280','1280*704')`; sampler `is_5b = out_dim == 48` + `extra_latents` path at nodes_sampler.py:755; shipped example node list = LoadImage, ImageResizeKJv2, WanVideoEncode, WanVideoEmptyEmbeds, WanVideoSampler (NO ImageToVideoEncode); `nvidia-smi -L` GPU1 handle error; still 941×1672 PNG.

## 3. Consensus reviewer passes

| Seat | Verdict | Blockers | Non-blockers |
|---|---|---|---|
| GPT (bridge) | REVISE BEFORE EXECUTION | B1 admission boundary, B2 stills snapshot integrity, B3 timeout state reversal (reproduced) | N1–N5 |
| Opus (xhigh) | REVISE BEFORE EXECUTION | B1 WAN 1280×720 invalid on 5B, B2 wrong I2V chain (14B path), B3 LTX round-down letterboxes, B4 timeout + orphaned prompts, B5 live-tree build breaks restart gate | N1–N12 |

## 4. Agreement points

- Engine contract is pinned correctly by the plan (every adapter check passed on both seats).
- The proven Q3 graph is copied faithfully; sigmas, strengths, audio path, tiled decode all verified.
- D1–D4 and the operator/restart gates stand. No engine, ComfyUI, or paid-path changes.
- The WAN wrapper's T2V-only stills gap and hardcoded cfg are real.
- The interlock is advisory, not mutual exclusion (GPT N1 = Opus N1).
- Validation must run before the 202, not in the background worker (GPT B1 = Opus N2).
- Stills must be hashed as the exact bytes used, race-resistant (GPT B2 = Opus N6; GPT rates blocker, Opus non-blocker → **strictest credible wins: blocker**).
- Timeout lifecycle is defective (GPT B3 reproduced it; Opus B4 adds the orphaned-prompt pileup and the LTX 429 consequence).

## 5. Disagreement matrix

**No conflicting findings.** Severity deltas resolved by the strictest-credible rule: stills integrity → blocker (C2); validation placement → blocker (C1). GPT's "pad not crop alone" math observation and Opus's "never pad, round up" amendment are compatible — Opus's rule satisfies both and reproduces the runbook precedent. GPT's caution against blind global `/interrupt` and Opus's interrupt-on-timeout requirement reconcile as: interrupt only after confirming via `/queue` that the running prompt is this wrapper's own; delete pending prompts by id.

## 6. Consolidated blockers (mandatory amendments)

- **C1 (GPT-B1, Opus-N2) — Admission boundary.** Schema, served-variant, and stills acceptance run synchronously BEFORE the 202 and before any queueing; background generation consumes the admitted snapshot. Socket-free ASGI/TestClient tests for both services: exact 400/429/503, zero ComfyUI submissions on refusal, valid 202 ids, status/output/404 behavior. ComfyUI `/prompt` 400 (node_errors, nothing queued) = definite 4xx; connection failure/timeout = 503 (Opus N4). FastAPI 422 default overridden to 400 `{error, detail}` via a RequestValidationError handler.
- **C2 (GPT-B2, Opus-N6) — Stills snapshot integrity.** Containment via `resolved.is_relative_to(root.resolve())` (no string prefix), regular file only, basename sanitized to `[A-Za-z0-9._-]`; read the file ONCE, hash those bytes, write the same bytes with exclusive `open(dst,'xb')` under a unique per-job name; never follow a pre-existing destination link; on failure remove temp material and submit no graph; clean copied inputs at terminal state. Deterministic replacement/content-change tests between validation and staging; exact destination-byte hash assertions; same-basename concurrent jobs. LTX requires image_path (I2V-only graph).
- **C3 (GPT-B3, Opus-B4b) — Terminal-state monotonicity.** Late executor results can never publish success/output for an expired job; terminal states stay terminal; expired jobs tracked as draining (resource ownership not released as if stopped). On timeout/cancel: if `/queue` shows THIS wrapper's prompt running → `POST /interrupt`; if pending → `POST /queue {"delete":[id]}`. Never blind-interrupt (could hit the other wrapper's job). Fake-client regressions: timeout→late success/error, monotonicity, ownership, next-job handoff. Same invariant in both wrappers.
- **C4 (Opus-B1) — WAN size mapping.** TI2V-5B needs multiples of 32 (vae_stride 16 × patch 2); 1280×720 is invalid (720→latent 45, odd, patchify mismatch). Map the request to **1280×736** (nearest /32 ≥ 720), generate, then ffmpeg center-crop 8 px per side to exact 1280×720. **Never pad.** Same size for the I2V still resize. Step 8 smoke must request **1280×720** (small frames/steps). "T2V byte-identical" narrowed to the proven 704×1280 default shape.
- **C5 (Opus-B2) — WAN I2V chain rewrite.** The planned `WanVideoImageToVideoEncode` chain is the 14B channel-concat path and crashes on 5B (96 channels into a 48-channel patch embedding). Correct chain (verified against the shipped 5B example + sampler code): **LoadImage (copied still) → core ImageScale (lanczos, C4 size, crop center) → WanVideoEncode (vae) → WanVideoEmptyEmbeds(width, height, num_frames, extra_latents) → sampler image_embeds**. KJNodes absent → core ImageScale, not ImageResizeKJv2; `WanVideoImageResizeToClosest` rounds to 16 — not used. Step 5 INPUT_TYPES read stays as confirmation; the example is WIP, so Step 8 visual still-fidelity check is the real proof.
- **C6 (Opus-B3) — LTX round-UP, never pad.** Stage-1 dims round UP to /32: 1280×720 → 640×384 → ×2 = 1280×768 → center-crop 24 rows per side → exact 1280×720. Reproduces the runbook precedent (540→544, crop 4/side) and the 1088×1920 golden. Fix the §2 test row ("crop 1280×720" from 704 was impossible) and Step 7 text. ~9% more stage-2 pixels, far inside the pilot envelope.
- **C7 (Opus-B4a, GPT-N3) — Timeout gate.** The frozen HG-2 clip (97f×50 steps×1280×720) has a ≥1472 s linear floor from live calibration vs the 600 s timeout — it WILL time out, retries pile orphaned prompts, then LTX gets 429s. Step 8 installs a drop-in raising `WAN_JOB_TIMEOUT_SECONDS` (and LTX equivalent), value derived from a MEASURED landscape run at ≥2× extrapolation, installed together with Jose's confirmed restart. "Smaller params" removed as an HG-2 option (frozen clip set, D4); small params only for wrapper smokes. Verify effective systemd env + engine wait/recovery budgets before HG-2. Do not present extrapolations as measured.
- **C8 (Opus-B5) — Worktree isolation.** `wan2.2.service` runs from the checkout with Restart=on-failure: building in-place means any crash/reboot restarts WAN on half-built code without confirmation, and `git checkout main` rollback would delete LTX's files. Build in `git worktree add /home/jarvis/Wan2.2-hg2 -b hg2-wrappers`; `ltx.service` points at the worktree; the main tree stays on main until Step 8 (fast-forward + Jose-confirmed restart). Rollbacks become truly independent.

## 7. Non-blockers

**Technical — applied with the blockers (no product judgment):** Opus N1 (asyncio.Lock around check+submit; same busy-check added to WAN; `WAN_GPU_IDS=0` drop-in; LTX queue depth 1; interlock labeled advisory) + the /health-as-interlock improvement (non-2xx when ComfyUI unhealthy or queue busy → engine refuses at its health gate, costing no attempt); Opus N3 (one variant setting drives schema default, validation, /health; bare-T2V regression); Opus N5 (num_frames drives nodes 8 AND 9; fps drives 5/9/19; node 31 filename parameterized; golden compares the prompt object; fixture pinned by sha256); Opus N7 (Step 0: separate test venv `--system-site-packages` — the shared venv is ComfyUI's runtime; conftest sets WAN_OUTPUT_DIR to tmp because config.py mkdirs at import); Opus N8 (T2V golden captured from unmodified 3a4b80b code, fixed seed); Opus N9 (blocking calls + ffmpeg in executor; completed only after ffmpeg + atomic rename; `-c:a copy`); Opus N10 (unit User=jarvis, WorkingDirectory/PYTHONPATH); GPT N2 (guidance fix applies to T2V and I2V; fps 24 hardcoded — documented for this fixed-24 stage); GPT N4 (offline ffmpeg/ffprobe fixture test: exact dims, audio retained, valid MP4, failed-tail handling; smoke base-vs-final wording); GPT N5 (verify host/network access policy at install — 0.0.0.0 bind is not itself tailnet-only proof; record actual pytest version/counts; no inherited numbers re-reported as verified).

**For Jose (product/hardware judgment — gate the live steps, not the build):**
- **J1 (Opus N11):** the staged still is **941×1672 portrait**, and it is the pilot reference whose prompt described "the woman … by the white SUV" — while both clip prompts describe a locksmith van. A 16:9 center crop keeps ~32% of the height. **Jose must look at the still before HG-2**; if it is the wrong subject, a new still means re-staging + a new sha256 in clips.json.
- **J2 (Opus N12):** **GPU1 reports "Unknown Error"**; only GPU0 is enumerated. Single-GPU ComfyUI on GPU0 is unaffected, but check the hardware before live smokes (and the WAN_GPU_IDS=0 drop-in makes the wrapper single-GPU too).
- **J3:** `local-services.json` model fields → `5b-gguf` / `ltx-2.5-q3` (Jose's file) before HG-2.
- **J4:** approve the measured timeout value at Step 8 (with the restart confirmation).

## 8. Corrected execution shape

Step 0 test venv + worktree (C8, N7) → Step 1 stills snapshot guard (C2) → Steps 2–4 LTX package with admission-before-202 (C1), round-up mapping (C6), terminal-state + interrupt discipline (C3), full parameter coverage (N5) → Step 5 WAN upgrade: size mapping (C4), corrected I2V chain (C5), admission move (C1), lifecycle fix (C3), variant unification (N3), guidance wiring (N2) → Step 6 offline suite in the test venv → Step 7 LTX smoke (Jose-authorized; J2 hardware check first) → Step 8 measured timeout drop-in (C7) + WAN_GPU_IDS=0 + fast-forward + Jose-confirmed restart + WAN smoke at a 1280×720 request (C4) → Step 9 Jose's HG-2 (J1 still review, J3 tags, J4 timeout approved; pre-flight /queue empty + nvidia-smi).

## 9. Direct answer to Jose

Both reviewers independently say: right architecture, wrong execution details — fix eight bounded things before coding. Two of them (the invalid 1280×720 WAN size and the 14B-only I2V chain) would have failed your HG-2 WAN take while the planned smoke passed anyway; Opus caught them by reading the actual node code on the ROG, and I re-verified both against the peer myself. The timeout defect GPT reproduced is real and pre-existing. All fixes are plan/design amendments — no engine change, no second generator, no new infrastructure. After application, GPT asks for closure on the amended snapshot (a round-2 check); Opus considers the plan safe to execute once amended. Also before your clips: look at the staged still (it's portrait and may show the wrong subject) and note GPU1 is reporting a hardware error.
