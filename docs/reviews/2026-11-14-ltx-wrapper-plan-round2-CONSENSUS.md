# CONSENSUS REPORT — LTX wrapper + WAN upgrade plan (round 2 closure)

**Date:** 2026-11-14
**Reviewers:** GPT/Hermes `gpt-6.1-sol-900k` (bridge run 20261114T142444.985947Z-9a99c4d730) + Claude Opus 5.5 (xhigh, 19 turns, read-only + live peer SSH)
**Source reviewed:** plan v1.1 (sha256 3709ba4ceacd406c5ba41b81483938ddc5b1c9c5224b0a3bc0e2218b974c3fee)
**Pins:** branch main, HEAD 4b791db, fingerprint e9be8e15… reproduced by both seats; peer WAN clean at 3a4b80b, unchanged on closing reads.
**Completion barrier:** both seats EXIT=0; full outputs read and reconciled.

## 1. Executive verdict

**REVISE BEFORE EXECUTION — both seats, with exactly two distinct new blockers between them and no conflicts.** All round-1 findings close in substance (GPT: 30 CLOSED / 3 PARTIAL of 33, the three PARTIALs being one shared residual; Opus: 32 CLOSED / 1 PARTIAL of 33). Both seats characterize the remaining fixes as **mechanical text amendments, not design changes**, and both pre-authorize closure by text check: Opus — "a text check of that amendment is enough to close it; no new design review is needed"; GPT — amend, then close the amended snapshot. **Applied the same day as plan v1.2** (C9, C10 + all round-2 non-blockers); a narrow round-3 text-check pass is the closure gate before Step 1.

## 2. The two new blockers (consolidated)

- **C9 (GPT B-new-1 = Opus NB-3) — cancellation must be prompt-targeted.** v1.1's check-then-global-interrupt pattern can interrupt the OTHER wrapper's prompt when the queue advances between the two requests. GPT executed the live server's actual `post_interrupt` handler with a fake queue: empty body → `INTERRUPTED_OTHER_PROMPT`; `{"prompt_id": own}` → no interruption. The live ComfyUI already supports the targeted body (server.py:1257–1286). Amendment: targeted interrupt only, never global/fallback; pending-delete by id then re-read (200 ≠ removed; may have moved to running); draining job keeps slot + input until the owned prompt is absent/terminal and the executor quiesced; deterministic queue-transition regressions. → v1.2 §5, §2.4.
- **C10 (Opus B-new-1 = GPT N-new-1) — the Step 0 test venv cannot work as written.** `--system-site-packages` exposes the BASE interpreter's dirs, not the shared venv's; fastapi/pydantic/httpx/uvicorn/starlette exist only in `/home/jarvis/.venv/wan2.2` (3.12.3, include-system-site-packages=false); the peer's default `python3` is now 3.14.4 and sees none of them. Every obvious workaround breaks a rule (installing into the shared venv, unpinned versions, wrong interpreter). Amendment: `/usr/bin/python3.12 -m venv` + pytest only + read-only `.pth` appending the shared site-packages; pinned test command with the worktree on sys.path; import/collection preflight; record interpreter + dependency versions/origins. → v1.2 §0.7, Step 0.

## 3. What round 2 verified (evidence highlights)

- **Both seats re-verified the round-1 fixes against live peer code:** core ImageScale inputs; WanVideoEmptyEmbeds extra_latents → index-0 insert; WanVideoEncode required inputs (incl. five tile scalars); the 5B sampler path works with the current unipc scheduler (Pusa not required); the shipped WIP example wiring matches the plan's chain; mapping math recomputed independently by both seats (LTX 640×384→1280×768→crop 24/side; WAN 1280×736→crop 8/side; golden + runbook cases reproduce; padding mathematically impossible); timeout floor recomputed from live calibration (1472 s at 720 rows; ≈1504 s at the generated 736 — estimator outputs, not measurements).
- **GPT additionally:** executed the real adapter + localTestHandler with injected fakes (health interlock refuses at zero ledger cost; cancelled→poll_failure); byte-verified the frozen engine copies against `git show 4d4e4fa`; reproduced all pins before/after; confirmed queue-delete/interrupt API shapes and the unit drop-in mechanism.
- **Opus additionally:** ffprobe of the proven LTX pilot output (aac audio → `-c:a copy` valid); found the WAN worker's hardcoded home paths (calibration + outputs) that would let tests write into the LIVE service's state (NB-1); found the `/cancel` revival bug (NB-6); named the Step 8 measurement path and daemon-reload (NB-8).

## 4. Non-blockers folded into v1.2

Opus NB-1 (conftest HOME isolation + config-routed writes), NB-2 (shared ffmpeg tail; WAN rename-before-completed), NB-4 (lock spans admission + reservation; /prompt call site = worker), NB-5 (busy-check before staging; refusal cleanup), NB-6 (/cancel monotonic), NB-7 (tile scalars asserted), NB-8 (measurement path, daemon-reload, LTX restart note, floor labeling); GPT N-new-1 (interpreter/versions — merged into C10), N-new-2 (provenance self-approval is history; carry the actual closure result + reviewed hash — done in the v1.2 log).

## 5. Disagreement matrix

None. The seats' blocker sets are the same two issues seen from different angles (GPT found the interrupt race by executing the handler; Opus found the venv defect by reading pyvenv.cfg and probing interpreters; each listed the other's finding as a non-blocker — strictest-credible rule makes both blockers). D1–D4 and J1–J4 untouched, as both seats instructed.

## 6. Corrected execution shape

v1.2 = v1.1 + C9/C10 + the folded non-blockers. Step 0 now builds a working, pinned test environment before anything else; §5 cancellation is prompt-targeted with draining ownership. Everything else stands. **Closure gate:** narrow round-3 text check that C9/C10 landed as required (both seats pre-authorized this; no new design review). Then Step 1.

## 7. Direct answer to Jose

The closure pass did its job: 32 of 33 findings closed outright, and the two residuals are small, provable, and now fixed in v1.2 — one safety race (interrupt could hit the other wrapper's job; the server already supports the targeted fix) and one setup defect (the test venv as specified couldn't import the runtime stack). Both reviewers say no further design review is needed — just verify the amended text. That verification is the narrow round-3 pass; when it returns clean, the build starts at Step 0.
