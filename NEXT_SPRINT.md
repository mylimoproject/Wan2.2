# NEXT_SPRINT — Wan2.2 (local video)

Last updated: 2026-11-14 (HG-2 wrapper build: Step 5 WAN upgrade built on the peer; Steps 0–6 green offline)

**What this is.** Jose's fork of `github.com/mylimoproject/Wan2.2`, used as a zero-cost **implementation and test harness** for the Locksmith ads pipeline. Real ads are produced on a paid API model: do not optimize this box for production throughput, and do not tune quality for final output.

**Where it runs.** The serving stack is on the peer **jarvis-rog-x570** (Tailscale `100.105.156.94`), not on jarvis-sister. This checkout is the source clone only; the build happens in the peer worktree `/home/jarvis/Wan2.2-hg2` (branch `hg2-wrappers` off `3a4b80b`).

**State (verified 2026-11-14).** WAN wrapper :8765 healthy (serves 5b-gguf), ComfyUI :8188 active; **GPU1 reports "Unknown Error"** (only GPU0 enumerated). HG-2 wrapper build: plan **v1.3 CLOSED FOR EXECUTION** after 4 consensus rounds (GPT bridge + Opus; inputs, 7 verdicts, reconciled reports in `docs/reviews/`). **Steps 0–5 complete** in the peer worktree (`14b7461`): isolated 3.12 test venv, stills snapshot guard + shared ffmpeg tail (`local_media.py`), full `ltx_service`, and the **WAN upgrade** — 32-grid size mapping (1280×720→1280×736→exact crop), 5B I2V chain via `extra_latents` (INPUT_TYPES confirmed on the peer first), admission before 202, prompt-targeted lifecycle, `5b-gguf` variant unification, guidance wiring, config-routed output/calibration paths, monotonic `/cancel`; T2V golden byte-identical. **Step 6 closed by record:** both-wrapper preflight green + full suite **150 collected, 147 passed, 3 route-exclusive skips**. Live tree and services untouched. **Next: Step 7, Jose-gated** (J2 GPU1 check → `ltx.service` install with sudo → LTX live smoke). Detail: `docs/2026-11-14-ltx-wrapper-implementation-plan.md` + worktree `BUILD_LOG.md`.

**Divergence.** Sister `main` ahead of origin (3 prior docs commits + this session's); peer `main` holds 2 unpushed progress/ETA commits; peer `hg2-wrappers` holds the build WIP commits (Steps 0–4 `82f2c5f`, Step 5 `14b7461`). Nothing pushed anywhere; publishing is Jose's.

**Rulings that constrain this project.** Implementation and test harness only (Jose, 2026-10-18). One video-generator service at a time (Jose, 2026-11-01) — the LTX wrapper fronts the shared ComfyUI; the dual-GPU orchestrator spec is a gated future R&D track (`docs/2026-11-14-orchestrator-spec-analysis.md`). Live smokes, `--execute` takes and service restarts are Jose's alone; agents build and offline-test. The sister's `~/Downloads/WAN2.2` (71 GB) is Jose's to move; do not delete it.

**Next, in order:** 1. Plan v1.3 Steps 7–9 are Jose-gated live steps: J2 GPU1 check → `ltx.service` install (sudo) → LTX live smoke → Step 8 measured timeout + confirmed WAN restart + WAN I2V smoke → Step 9 HG-2 `--execute` takes (one route at a time). Smoke scripts (`scripts/ltx-smoke.sh`, `scripts/wan-i2v-smoke.sh`) are written at those steps. 2. J1 closed (still subject approved 2026-11-14); J2/J3/J4 below remain.

**JOSE:** J2 — check the GPU1 "Unknown Error" hardware before any live smoke (build is single-GPU-safe on GPU0).
**JOSE:** J3 — set `local-services.json` model fields to `5b-gguf` / `ltx-2.5-q3` before HG-2 (your file).
**JOSE:** J4/Step 8 — approve the measured WAN timeout value and confirm the `wan2.2.service` restart.
**JOSE:** the live LTX/WAN smokes and the HG-2 `--execute` takes are yours to run (exact commands in plan Steps 7–9).
**JOSE:** decide whether the sister docs commits, the peer's two progress/ETA commits, and the `hg2-wrappers` build commit should be published; nothing has been pushed.
