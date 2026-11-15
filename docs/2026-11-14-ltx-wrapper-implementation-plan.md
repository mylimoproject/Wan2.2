# Implementation plan — LTX wrapper + WAN stills/I2V upgrade (HG-2)

Version: v1.3
**Date:** 2026-11-14 · **Status:** CLOSED FOR EXECUTION — round-4 micro closure **APPROVE** (GPT run 20261114T145145.232450Z-447817330c, reviewed v1.3 sha256 3ae1bcf8a3c0d750f37fc5cc0af8529d2c306712cf2baa5999d65d91036e8ed0); Opus round-3 APPROVE carries forward. J1 confirmed by Jose 2026-11-14. Build authorized ("closure, then build"); live smokes, HG-2 execution and the WAN restart remain Jose-gated (this approval does not authorize them).
**Scope doc:** `2026-11-14-ltx-wrapper-scope.md` (DECIDED: D1 shared :8188, D2 Q3, D3 LTX+WAN) · **Spec analysis:** `2026-11-14-orchestrator-spec-analysis.md`
**Consensus:** round 1 `reviews/2026-11-14-ltx-wrapper-plan-round1-CONSENSUS.md`; round 2 `reviews/2026-11-14-ltx-wrapper-plan-round2-CONSENSUS.md`; round 3 verdicts `reviews/2026-11-14-ltx-wrapper-plan-round3-{GPT,OPUS}-VERDICT.md`
**Build site:** peer worktree `/home/jarvis/Wan2.2-hg2` (branch `hg2-wrappers` off `3a4b80b`) on jarvis-rog-x570 · **Engine contract:** Locksmith APP ads provider modules (S4L, frozen at 4d4e4fa, CI-green)

## 0. Ground rules

1. No Locksmith engine changes. The contract in §1 is pinned by the adapter and its offline tests.
2. One generator: the single shared ComfyUI :8188. `comfyui.service` is never modified, stopped or restarted by this build.
3. `wan2.2.service` restart happens only at Step 8, only with Jose's explicit confirmation.
4. **Worktree isolation (C8):** build in `git worktree add /home/jarvis/Wan2.2-hg2 -b hg2-wrappers` from the peer checkout. The live tree `/home/jarvis/Wan2.2` stays on `main` — `wan2.2.service` has `Restart=on-failure`, so an in-place build would let any crash/reboot restart WAN on half-built code without confirmation. `ltx.service` points at the worktree. WAN moves only at Step 8 by fast-forward + confirmed restart. Rollbacks are independent: LTX = stop/disable its unit; WAN = the main tree never moved before Step 8.
5. No keys, no egress beyond localhost ComfyUI. Bind posture unchanged from WAN (0.0.0.0); at install, verify the host/network access policy actually restricts reachability to the tailnet (the bind alone is not proof).
6. HG-2 `--execute` runs and live smokes are Jose's (operator policy A1(b)). Agents build and offline-test.
7. **Test environment (C10):** the shared venv `/home/jarvis/.venv/wan2.2` (Python 3.12.3) is ComfyUI's runtime and holds the ONLY copies of fastapi/pydantic/httpx/uvicorn/starlette; `--system-site-packages` does NOT expose them (it exposes the base interpreter's dirs; the peer's default `python3` is now 3.14.4 and sees none of them). Therefore: create `/home/jarvis/.venv/wan2.2-hg2-tests` with **`/usr/bin/python3.12 -m venv`**, install **pytest only** into it, and add a `.pth` file appending `/home/jarvis/.venv/wan2.2/lib/python3.12/site-packages` **read-only**. **Never install into the shared venv.** The exact test command is pinned: `cd /home/jarvis/Wan2.2-hg2 && WAN_OUTPUT_DIR=<tmp> LTX_OUTPUT_DIR=<tmp> /home/jarvis/.venv/wan2.2-hg2-tests/bin/python -m pytest tests/` with the worktree root on `sys.path` (pytest `pythonpath` ini or conftest).
   **Preflight scheduling (R3-1):** Step 0 runs a **dependency/setup preflight only**: with both output-dir env vars and a temporary HOME set before import, import fastapi, pydantic, httpx, starlette and the **existing unmodified wan_service**; assert the **third-party runtime packages** resolve from the shared venv's site-packages (NOT a user site) — application code (wan_service, later ltx_service/local_media) resolves from the worktree root on sys.path; never search for or install application packages into the shared venv (round-4 referent clarification); record the interpreter (3.12.3) and the fastapi/pydantic/httpx versions **with their import origins** alongside pytest's version; **an empty test collection is accepted at Step 0** (no test modules exist yet). Each later step adds its newly created modules to the import check. The explicit **both-wrapper application import + full test-collection preflight runs after Step 4**, reruns after the Step 5 WAN changes, and gates the full suite at Step 6. The pinned interpreter/command, temporary HOME, env-vars-before-import, and shared-venv read-only rules never change.
8. No pushes; peer↔local reconciliation is Jose's (D5). No commits in a repo while a consensus bridge round is running against it.

## 1. The pinned contract (from the engine adapter — verbatim semantics)

- `GET /health` → any 2xx. **Interlock:** return non-2xx when ComfyUI `/system_stats` fails or `/queue` is not empty — the engine then refuses at its health gate before any ledger write, costing no attempt. The health gate runs once per command (not per seed retry), so 429 remains the in-run backstop.
- `POST /generate` body: `{prompt, negative_prompt, image_path, image_sha256, width, height, num_frames, fps, num_inference_steps, guidance_scale, seed, model_variant, output_format:"mp4"}`. **Answer within the engine's 60 s per-request timeout** — admission (§2) is synchronous and fast; generation is background.
  - **202** `{job_id}` with `job_id ~ ^[A-Za-z0-9_-]+$` → created.
  - **4xx except 429** → definite failure; body `error` or `detail` string (first 200 chars read). FastAPI's default 422 list-detail is overridden by a `RequestValidationError` handler returning 400 `{error, detail}`.
  - **429 / 5xx / network / timeout** → uncertain; the engine never re-POSTs; recovery via poll.
- `GET /status/{id}` → `{status: "queued"|"processing"|"completed"|"failed", error?}`; **404** = not_found; other non-2xx = poll_failure. The adapter reads `cancelled` as poll_failure — `/cancel` therefore reports cancelled jobs as status `failed` with error `cancelled`, never a lasting `cancelled` status, and a cancelled queued job can never be picked up by the process loop (NB-6).
- `GET /output/{id}` → MP4 bytes (engine bounds 250 MiB, checks `ftyp` at bytes 4–8); non-2xx preserves job+cost.
- No Authorization header; **no redirects** (`redirect_slashes=False`); `image_path` arrives **relative** and is joined to the service's stillsRoot; still bytes never cross the engine wire.
- `model_variant` must match the served variant or definite 4xx. **One setting drives schema default, validation and /health:** WAN `5b-gguf`, LTX `ltx-2.5-q3`. A bare request without `model_variant` gets the served default (regression-tested). Jose updates `local-services.json` model fields to exactly these tags before HG-2 (J3).
- Engine budgets (verified in jobs.mjs): polls every 30 s; 10 consecutive poll failures → uncertain; stale only after 24 h; ≤3 attempts per unit version with seed+1. The wrapper stays poll-responsive throughout (executor for blocking work).

## 2. Admission boundary (C1) and stills snapshot (C2)

**Admission runs synchronously in `main.py` BEFORE the 202 and before any queueing** (both services; WAN's checks move out of the worker), in this order: schema validation → served-variant check → **busy/unavailable rejection** (429 when the advisory interlock sees ComfyUI busy; 503 on connection failure/timeout) → **stills acceptance last** (so a refusal never leaks a staged copy — NB-5; any failure after staging still cleans up). An `asyncio.Lock` in `main.py` spans the busy-check **and the slot reservation** (NB-4); the worker consumes the reserved slot. Background generation consumes the admitted snapshot; a later ComfyUI failure (including a `/prompt` 400 with `node_errors` raised in the worker after the 202) is a job `failed` status, never retroactively the POST's answer. `/prompt` is called **in the worker**, after the 202; admission itself makes no ComfyUI prompt submission. HTTP-level TestClient tests (shared fake-ComfyUI ASGI contract suite for BOTH wrappers) prove: exact 400/429/503 bodies, **zero ComfyUI prompt submissions on any refusal**, **no leaked input copies on refusal**, valid 202 ids, subsequent status/output/404 behavior, seed:null preservation, the engine's exact fixed request as a positive fixture, simultaneous admissions.

**Stills snapshot (`local_media.py`, shared):**
1. Join the relative `image_path` to stillsRoot; `resolved.is_relative_to(root.resolve())` (no string-prefix check); regular file only; refuse symlink escapes at every component (race-resistant opening, including ancestor substitution — a pathname precheck alone is not the invariant).
2. Sanitize basename to `[A-Za-z0-9._-]` (ComfyUI gives ` [output]` and subpaths special meaning).
3. **Read the file once, hash those exact bytes, compare to `image_sha256`; write those same bytes** to a unique per-job destination in ComfyUI/input with exclusive `open(dst,'xb')` — never reopen the source for copying, never follow a pre-existing destination link. On any failure: remove temp material, submit no graph, definite 4xx.
4. Clean copied inputs when the job reaches a terminal state **and its owned ComfyUI prompt is absent/terminal and the executor quiesced** (never delete while a prompt is still draining). LTX **requires** `image_path` (its graph is I2V-only).
5. Tests: traversal/absolute/symlink refusal; missing file; hash mismatch; deterministic content replacement between validation and staging; exact destination-byte hash assertion; concurrent same-basename jobs; relative-path join; **copied input removed only under the §2.4 condition (terminal AND owned prompt absent/terminal AND executor quiesced)**; refusal leaves no copy.

**Shared media tail (NB-2):** `local_media.py` also owns the ffmpeg exact-size tail (crop, `-c:a copy` where audio exists) used by BOTH wrappers — WAN never imports `ltx_service`. The tail runs in the executor; the output is atomically renamed into place; `completed` is set only after the rename; an expired-job check precedes publication. Offline fixture tests for both routes (WAN: exact 1280×720 from a 1280×736 fixture; LTX: exact dims, audio retained, valid MP4, failed-tail handling).

## 3. Files

**New (peer worktree):**
| File | Content |
|---|---|
| `local_media.py` | the §2 snapshot guard + the shared ffmpeg tail (both services) |
| `ltx_service/__init__.py`, `config.py`, `schemas.py` | `LTX_*` env: port 8766, stillsRoot `/home/jarvis/ltx-stills`, output dir `~/.local/share/ltx2.5/outputs`, **queue depth 1**, job timeout 900 s default (Step 8 gate), served variant `ltx-2.5-q3`, ComfyUI URL + input dir; `image_sha256` required with `image_path` (hex64) |
| `ltx_service/graph.py` | parameterized builder from the proven Q3 JSON (§4 mapping); golden-tested against the fixture pinned by sha256 |
| `ltx_service/worker.py` | single worker consuming the reserved slot; submit → poll history (5 s) → download → shared ffmpeg tail → atomic rename → `completed`; blocking calls in an executor; lifecycle per §5 |
| `ltx_service/main.py` | §2 admission (lock spans busy-check + reservation) + the four endpoints (+`/cancel` per §1); `redirect_slashes=False` |
| `tests/…` | `test_local_media.py` (snapshot + tail fixtures), `test_ltx_schemas.py`, `test_ltx_graph.py` (golden compares the **prompt object**; fixture sha256-pinned), `test_ltx_mapping.py`, `test_wan_i2v_graph.py` (asserts ALL required `WanVideoEncode` inputs incl. the five tile scalars — NB-7), `test_wan_size_mapping.py`, `test_interlock.py` (simultaneous admissions, busy→429, /health non-2xx when queue busy), `test_admission_http.py` (shared contract suite, both wrappers), `test_lifecycle.py` (§5 regressions incl. the C9 queue-transition cases and cancel-while-queued), `conftest.py` (**HOME set to a temp dir before imports**; `WAN_OUTPUT_DIR`/`LTX_OUTPUT_DIR` tmp; worktree root on sys.path; asserts the real home is unchanged — NB-1) |
| `scripts/ltx-smoke.sh`, `scripts/wan-i2v-smoke.sh` | curl sequences (Jose runs); ffprobe + sha256; small params; **WAN smoke requests 1280×720** |
| `systemd/ltx.service` | `User=jarvis` (stills are 0600), WorkingDirectory + PYTHONPATH = the **worktree**, shared-runtime uvicorn `ltx_service.main:app --host 0.0.0.0 --port 8766 --workers 1`, Restart=on-failure; install needs sudo (Jose); enabled only after smoke |

**Modified (peer worktree):**
| File | Change |
|---|---|
| `wan_service/schemas.py` | `image_sha256` (required with image_path, hex64); variant default driven by the single served-variant setting |
| `wan_service/config.py` | stillsRoot `/home/jarvis/wan-stills`, served variant `5b-gguf`, ComfyUI input dir |
| `wan_service/main.py` | admission moved here (§2, lock + reservation before `pool.submit`); 400 handler; `redirect_slashes=False`; `/cancel` monotonic: status `failed`, error `cancelled`, never revived by the loop |
| `wan_service/worker.py` | **size mapping (§4b)**; **I2V chain (§4b)**; `guidance_scale` wired to sampler cfg for T2V and I2V (fps stays hardcoded 24 — documented); lifecycle per §5; **all output writes through `config.OUTPUT_DIR`** (the current code hardcodes `~/.local/share/wan2.2/outputs` and `CALIBRATION_PATH` under `Path.home()` — NB-1); shared ffmpeg tail + rename-before-completed; T2V graph byte-identical **for the proven 704×1280 default shape with default cfg** (golden captured from unmodified 3a4b80b code, fixed seed, before any edit) |

**Never touched:** `comfyui.service`, ComfyUI itself, custom nodes, model files, the Locksmith engine, paid paths.

## 4. LTX parameter mapping (D4 — wrapper-owned; C6 round-UP)

| Engine field | Mapping |
|---|---|
| width×height | stage1 = half-res, each dim rounded **UP** to /32 (`32*ceil(req/64)`): 1280×720 → 640×384; ×2 upsample → 1280×768; ffmpeg **center-crop 24 rows per side** → exact 1280×720. **Never pad** (2·ceil32(⌈w/2⌉) ≥ w always). Reproduces the runbook precedent (540→544, crop 4/side) and the 1088×1920 golden (544×960 stage, no crop). +9.09% stage-2 pixels vs the old round-down design — far inside the pilot envelope |
| num_frames | keep if ≡1 mod 8 (97 ✓); else snap to nearest 8k+1 ≥ 17; tie/minimum behavior explicit in tests. Drives **node 8 length AND node 9 frames_number** |
| fps | 24 → drives **nodes 5, 9 and 19** |
| num_inference_steps | ignored; fixed proven sigmas: stage1 `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0` (8 steps), stage2 `0.85, 0.7250, 0.4219, 0.0` (3 steps) |
| guidance_scale | fixed 1.0 (distilled dual CFG) |
| seed | one random draw when null, **reused in both noise nodes**; else the engine's integer in both |
| model_variant | must equal `ltx-2.5-q3` (default when omitted) |
| still | LoadImage ← §2 snapshot copy (**node 31 filename parameterized**); LTXVPreprocess img_compression 18; I2V inplace strength 0.7 (stage1) / 1.0 (stage2) |
| audio | kept; SaveVideo h264, `format:auto`, per-job prefix `ltx25-engine/{job_id}`; tail uses `-c:a copy` (pilot output is aac — stream copy valid) |

## 4b. WAN mapping and I2V chain (C4, C5 — verified against peer code, round 2)

- **Size:** TI2V-5B requires multiples of 32 (vae_stride 16 × patch 2); 720 is invalid (latent 45, odd → patchify mismatch). Map each dim to `32*ceil(req/32)`: 1280×720 → **1280×736** (latent 46 → 23 patches, integer ✓), generate, then the shared ffmpeg tail center-crops 8 px per side → exact 1280×720. **Never pad.** The I2V still resize uses the same generated size (1280×736 is /16-clean for `WanVideoEncode`, latent 46×80 T=1, matching the index-0 insert). The proven 704×1280 shape passes through unchanged. Mapping tests included.
- **I2V chain (the 14B `WanVideoImageToVideoEncode` channel-concat path crashes on 5B):** `LoadImage` (§2 copy) → **core `ImageScale`** (`upscale_method:"lanczos"`, generated width/height, `crop:"center"` — KJNodes absent; `WanVideoImageResizeToClosest` rounds to 16, unsafe) → **`WanVideoEncode`** with ALL required inputs: `vae`, `image`, **`enable_vae_tiling:false, tile_x:272, tile_y:272, tile_stride_x:144, tile_stride_y:128`** (the shipped example's values; missing scalars → `/prompt` 400 — NB-7) → **`WanVideoEmptyEmbeds`(width, height, num_frames, extra_latents)** → node 6 `image_embeds`. The current `unipc` scheduler works (clean latents skipped for non-Pusa schedulers; verified in nodes_sampler.py). T2V keeps node 5 unchanged. Step 5 reads the nodes' `INPUT_TYPES` on the peer as confirmation; the shipped example is WIP, so the Step 8 visual still-fidelity check is the real proof.
- **Variant:** one setting (`5b-gguf`) drives schema default, validation and /health; bare-T2V regression test.

## 5. Worker lifecycle — terminal states are terminal; cancellation is prompt-targeted (C3, C9)

Both wrappers:
- A timed-out or cancelled job is `failed` **forever**: late executor results can never publish success or output for an expired job; the job is tracked as *draining*; the next job hands off only when the slot is genuinely free.
- **Cancellation is prompt-targeted (C9):** `POST /interrupt` with JSON **`{"prompt_id": <own_comfy_prompt_id>}`** and Content-Type application/json — the live ComfyUI server checks the id against running entries and skips interruption when absent (verified in server.py and by executing the handler). **Never send an empty-body/global interrupt; never fall back to one** when ownership is absent, changed, or uncheckable. A check-then-act preflight is NOT the invariant: between a `/queue` check and a global interrupt the queue can advance to the other wrapper's prompt.
- Pending owned prompt: `POST /queue {"delete":[id]}`, then **re-read queue/history** — a 200 does not prove removal, and the prompt may have moved to running; if running, use the same targeted interrupt.
- **Draining ownership:** the failed job keeps its slot and its input snapshot until the owned prompt is actually absent/terminal AND the executor has quiesced; a deletion/interrupt HTTP 200 alone never frees the slot or deletes the input. Monotonic failed status; no late output publication.
- Fake-client lifecycle regressions (both wrappers): timeout→late success; timeout→late error; terminal-state monotonicity; own-running→other-running between check and action; own-pending→own-running before delete; delete/interrupt no-op or transport failure; no known prompt id; retained ownership/input while draining; own-prompt cleanup before next-job handoff; cancel-while-queued never revived by the process loop. **The exact-interrupt-JSON, zero-global-interrupts and no-foreign-prompt-action assertions apply to EVERY case** — especially no-known-prompt-id and transport failure, where a fallback would otherwise appear.
- The interlock is **advisory**; ComfyUI serializes internally, the /health gate refuses when busy, and Jose's sequential route policy stands. No distributed scheduler. `WAN_GPU_IDS=0` in the Step 8 drop-in (one ComfyUI, one main device; GPU1 currently faulted — J2).

## 6. Step order (each step ends with its offline tests green under the §0.7 pinned command)

0. **Setup:** peer worktree (`git worktree add /home/jarvis/Wan2.2-hg2 -b hg2-wrappers`); test venv per §0.7 (**`/usr/bin/python3.12 -m venv`**, pytest only, read-only `.pth` to the shared site-packages); **dependency/setup preflight per §0.7** (runtime deps + unmodified wan_service importable from the shared site-packages — not a user site; env vars + temp HOME set before import; empty collection accepted); record interpreter + fastapi/pydantic/httpx versions and origins + pytest version; capture the T2V golden from unmodified 3a4b80b code (fixed seed); pin the Q3 fixture by sha256.
1. `local_media.py` snapshot + shared tail + tests (§2); add local_media to the import check.
2. `ltx_service` config/schemas + tests; add the new modules to the import check.
3. `ltx_service/graph.py` + golden/mapping tests (§4).
4. `ltx_service/worker.py` + `main.py` + admission/lifecycle/interlock tests (§§2, 5; fake ComfyUI, no sockets); **then run the explicit both-wrapper application import + full test-collection preflight (§0.7)**.
5. WAN upgrade: read `INPUT_TYPES` on the peer first (confirm §4b incl. the five tile scalars), then size mapping, I2V chain, admission move, lifecycle fix, variant unification, guidance wiring, output paths through config, `/cancel` monotonicity + tests (T2V golden byte-identical for the proven default shape); **rerun the both-wrapper preflight after the WAN changes**.
6. **Both-wrapper preflight green**, then full offline suite green (record actual collection and pass counts — no inherited numbers).
7. Install `ltx.service` (sudo — Jose; verify network policy), start LTX only. **J2 hardware check first** (GPU1 fault). **LTX live smoke** (Jose-authorized): staged still, 33 frames, **final-request 1280×720** (mapping yields 640×384 base), 8+3; ffprobe (h264 + audio, exact dims), sha256 recorded.
8. **Timeout gate (C7) + deployment:** measure a mid-size landscape WAN job **through the still-live 3a4b80b wrapper** (T2V, 600 s timeout) at a 32-grid size such as 1280×736 sized to finish well under 600 s (or direct ComfyUI submission) — the HG-2 linear floor at the GENERATED 1280×736 shape is ≈1504 s (the 1472 s figure was computed at 720 rows; both are estimator outputs, not measurements; attention makes the real time longer). Derive `WAN_JOB_TIMEOUT_SECONDS` ≥ 2× the measured/extrapolated HG-2 time. Install drop-ins (`wan2.2.service.d/*.conf`: `WAN_JOB_TIMEOUT_SECONDS`, `WAN_GPU_IDS=0`; LTX equivalent), **`systemctl daemon-reload`**, fast-forward main, **Jose-confirmed WAN restart** (an LTX drop-in implies an LTX restart — harmless, not covered by the WAN confirmation). Verify effective systemd env. Then **WAN I2V smoke at a 1280×720 request** (17 frames, 10 steps): exact dims out, still fidelity visually confirmed.
9. **Jose's HG-2** (gates: J1 still reviewed, J3 tags set, J4 timeout approved; pre-flight `/queue` empty + `nvidia-smi`): `local-test localtest-hg2 --route local-wan --max-cost-usd 0 --execute`, then `--route local-ltx` (one at a time). Verify job-state/3, one 0¢ `provider_reported` settle, output; visual review of both clips. Record in both trackers.

**Rollback:** LTX = `systemctl stop/disable ltx` (worktree untouched by WAN). WAN = main tree never moved before Step 8; after Step 8, revert the fast-forward + confirmed restart. ComfyUI and the engine never change.

## 7. Known limitations (accepted for the test stage)

- In-memory job tables: a wrapper restart loses jobs → engine recovery settles the 0¢ `reservation_fallback` (safe at 0¢; durable state is later hardening). Distinct from the C3/C9 live state reversal and foreign-interrupt risks, which are fixed by design.
- Advisory interlock (see §5); sequential live use is the operator policy.
- HG-2 runtime is bounded by the Step 8 measured timeout, not guessed; extrapolations are never reported as measured.

## 8. Acceptance

Offline suite green under the pinned §0.7 command (recorded interpreter/versions/counts); both live smokes green with the staged still at a **1280×720 request** (hash-verified, exact dims, audio on LTX); engine dry runs green; then Jose's HG-2 produces two takes with job-state/3 + 0¢ ledger lines + outputs he has watched. No change to ComfyUI, the engine, or paid paths.

## 9. Jose gates (operator/product judgment — gate the live steps, not the build)

- **J1: CLOSED — Jose confirmed 2026-11-14 ("j1=yes"): the staged still's subject is approved as-is; no re-stage.** Facts for the record: the still is 941×1672 portrait (the pilot reference); a 16:9 center crop keeps ~31.7% of the height — accepted by Jose with the subject approval.
- **J2:** GPU1 reports "Unknown Error" (only GPU0 enumerated). Check hardware before live smokes; the build is single-GPU-safe (WAN_GPU_IDS=0, ComfyUI on GPU0).
- **J3:** `local-services.json` model fields → `5b-gguf` / `ltx-2.5-q3` (Jose's file) before HG-2.
- **J4:** approve the measured Step 8 timeout value together with the restart confirmation.

## Provenance — Amendments Log

- **2026-11-14 consensus-review-amended** to v1.1 (from v1.0 unversioned)
  - Source review: `/home/jose-a-pichardo/Wan2.2/docs/reviews/2026-11-14-ltx-wrapper-plan-round1-CONSENSUS.md`
  - Verdict in source review: REVISE BEFORE EXECUTION (both seats: GPT gpt-6.1-sol-900k via bridge; Opus claude-opus-5-5 xhigh)
  - Amendments applied: C1–C8 (admission boundary; stills snapshot; terminal lifecycle; WAN size mapping; 5B I2V chain; LTX round-up; measured timeout gate; worktree isolation) + round-1 technical non-blockers (see round-1 consensus report §7)
  - Amendments deferred: none · Needs re-check: round-2 closure (performed, below)
  - Post-apply verdict: APPROVED by apply-protocol — **superseded by round-2 independent review (GPT N-new-2: provenance self-approval is history, not closure evidence)**
- **2026-11-14 consensus-review-amended** to v1.2 (from v1.1)
  - Source reviews: `reviews/2026-11-14-ltx-wrapper-plan-round2-GPT-VERDICT.md` (run 20261114T142444.985947Z-9a99c4d730; reviewed plan sha256 3709ba4ceacd406c5ba41b81483938ddc5b1c9c5224b0a3bc0e2218b974c3fee) and `reviews/2026-11-14-ltx-wrapper-plan-round2-OPUS-VERDICT.md`
  - Round-2 closure result carried forward: GPT 30 CLOSED / 3 PARTIAL (one shared residual) / 0 NOT ADDRESSED of 33; Opus 32 CLOSED / 1 PARTIAL (Opus-N7) of 33. Both verdicts REVISE BEFORE EXECUTION with exactly two distinct new blockers between them (no conflicts):
  - Amendments applied: C9 (prompt-targeted interrupt, draining ownership, queue-transition regressions) and C10 (python3.12 test venv + read-only .pth + pinned command + recorded versions/origins); round-2 non-blockers NB-1, NB-2, NB-4, NB-5, NB-6, NB-7, NB-8 and GPT N-new-2 folded
  - Amendments deferred: none · Needs re-check: narrow round-3 text check (performed, below)
  - Post-apply verdict: APPROVED pending the narrow round-3 text-check closure of C9/C10
- **2026-11-14 consensus-review-amended** to v1.3 (from v1.2)
  - Source reviews: `reviews/2026-11-14-ltx-wrapper-plan-round3-GPT-VERDICT.md` (run 20261114T143947.513834Z-b9421c4826; reviewed plan sha256 756e6915f09c38dd4f370a16f8eb4c23ccaab6b2220e5619da030b2950dfa147) and `reviews/2026-11-14-ltx-wrapper-plan-round3-OPUS-VERDICT.md` (same v1.2 hash)
  - Round-3 result: **Opus APPROVE** (C9 CLOSED, C10 CLOSED, all non-blockers present; four packet notes; "no further consensus round"); **GPT REVISE** on one amendment-introduced sequencing item **R3-1** (Step 0 demanded both wrappers importable before Steps 1–4 create them) with an exact required minimal amendment; C9 CLOSED, C10 mechanism accepted
  - Amendments applied:
    - R3-1 (GPT, verbatim per its required amendment): Step 0 = dependency/setup preflight only (runtime deps + unmodified wan_service, shared-site-packages origin assertion, empty collection accepted); incremental per-step import checks; explicit both-wrapper import + collection preflight after Step 4, rerun after Step 5, gating Step 6 (§0.7, Steps 0–6)
    - Opus round-3 packet notes: §2.5 cleanup test aligned to the §2.4 draining condition; zero-global-interrupts/exact-JSON/no-foreign-action assertions applied to EVERY lifecycle case; /cancel wording pinned to status failed + error cancelled; Step 0 preflight asserts imports come from the shared venv site-packages, not a user site
  - Amendments deferred: none
  - Amendments needing re-check: R3-1 closure — micro round-4 text check, GPT seat only (Opus approved v1.2 and requested no further rounds; v1.3 changes only what the two seats asked for, so Opus's approval carries forward)
  - Memory-write trigger fired: yes — project_wan22_local_video updated (round-3 result, plan v1.3)
  - Post-apply verdict by consensus-protocol rules: APPROVED pending the micro round-4 closure of R3-1
- **2026-11-14 consensus-closed** at v1.3 (closure record; no version bump — one non-blocking referent clarification folded)
  - Source reviews: `reviews/2026-11-14-ltx-wrapper-plan-round3-{GPT,OPUS}-VERDICT.md`, `reviews/2026-11-14-ltx-wrapper-plan-round4-GPT-VERDICT.md` (run 20261114T145145.232450Z-447817330c, **APPROVE**, reviewed v1.3 sha256 3ae1bcf8a3c0d750f37fc5cc0af8529d2c306712cf2baa5999d65d91036e8ed0); reconciled in `reviews/2026-11-14-ltx-wrapper-plan-rounds3-4-CLOSURE.md`
  - R3-1 CLOSED (quoted evidence for every element); Opus packet notes LANDED; no new contradictions; Opus round-3 APPROVE carries forward (attributed as carry-forward, not a fresh v1.3 vote)
  - Clarification folded into §0.7: the shared-site-packages origin assertion applies to third-party runtime packages; application code resolves from the worktree root on sys.path
  - J1 CLOSED (Jose, "j1=yes", 2026-11-14); J2/J3/J4 remain live-step gates
  - Final state: **CLOSED FOR EXECUTION** — build Steps 0–6 authorized under Jose's "closure, then build" decision; live smokes, HG-2 and the WAN restart remain Jose's
