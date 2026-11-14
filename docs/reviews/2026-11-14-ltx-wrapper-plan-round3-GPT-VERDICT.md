# GPT VERDICT — LTX wrapper + WAN upgrade plan (round 3 text check)
Reviewer: GPT/Hermes, gpt-6.1-sol-900k, openai-codex; consensusbridge Round-B seat
Date: 2026-11-14

## Verdict
REVISE BEFORE EXECUTION

Decision: REVISE

C9 is CLOSED. C10's interpreter/package-isolation correction is present, but its newly specified Step 0 preflight requires both wrappers to be importable before the plan creates the LTX package. This is one amendment-introduced sequencing contradiction, not a reopened design finding. Split the dependency/setup preflight from the later both-wrapper import/collection gate; the exact correction is below. No changes to D1–D4 or J1–J4 are requested.

This is the GPT/Hermes vote on the exact v1.2 snapshot, not a claim that a fresh Opus round-3 vote has returned. The supplied Opus round-2 verdict was read and attributed to that artifact; no Opus/Claude endpoint was invoked, independently runtime-verified, or impersonated in this bounded pass. There is no established final-round bilateral disagreement on the sequencing finding, so no tie-break is requested.

### Snapshot and verification receipts

- Project root: `/home/jose-a-pichardo/Wan2.2`; branch `main`; HEAD `4b791dbfb940792178b8287fd5501bbf732fe9ae`. Root/branch/HEAD were checked before substantive judgment.
- The bridge's actual read-only `repo_snapshot` function reproduced the worktree fingerprint `4326575a8e7162a18905c1ae2642b5b4bd928979a606b44dbfa0c6d5c2b9de92`, input SHA256 `082db99c2f461c025b49576491dba88bc706b918531c9f50217f9a116b94341f`, and named ignored-source SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. All pins matched before review and again immediately before writing. The named ignored-source manifest is empty; the named ordinary untracked sources are covered by the worktree fingerprint. Protocol input/output exclusions follow the bridge implementation.
- Reviewed v1.2 plan SHA256: `756e6915f09c38dd4f370a16f8eb4c23ccaab6b2220e5619da030b2950dfa147`.
- Read the complete input, implementation plan, both round-2 verdicts, reconciled round-2 report, and all six named evidence siblings. Also read the scope, spec analysis, tracker, project manifest, Makefile, and existing test documentation/script.
- Recomputed the closure-table tallies from the actual round-2 rows: GPT 33 entries = 30 CLOSED / 3 PARTIAL / 0 NOT ADDRESSED; Opus 33 entries = 32 CLOSED / 1 PARTIAL / 0 NOT ADDRESSED. These reproduce the v1.2 provenance, not new claims that implementation tests passed.
- Bounded source spot checks: the captured WAN schemas/routes/worker still show the old cancellation and home-path behavior being corrected; the actual frozen adapter recognizes `failed`, not `cancelled`, and the LTX adapter shares that factory. CLI source places its health check before ledger/state-writing operations. These checks support C9/NB-1/NB-6 without reopening their agreed design.
- Parsed the captured Q3 prompt: 31 nodes, 41 links, zero dangling references, 8+3 sigma intervals. Parsed the frozen clip set: one clip, 1280×720, 97 frames, 24 fps, 50 steps, CFG 5, seed 1. The current v1.2 plan names nine proposed `test_*.py` modules plus `conftest.py`; these are creation tasks, not existing green tests.
- Live local discovery confirms this source clone has no `ltx_service`, `wan_service`, or `local_media.py`, no Python test modules under `tests`, and no workflow files under `.github/workflows`. The plan correctly targets the separate peer build. No root AGENTS.md, CLAUDE.md, .cursorrules, or AI_STATE.md exists here. The tracker labels its older divergence/service measurements historical; live origin divergence without fetching is 3 ahead / 0 behind.
- Per the narrow packet, no new peer-code expedition, service call, dependency installation, wrapper/GPU test, or external reviewer dispatch was performed. Peer runtime/package/API facts from round 2 remain attributed evidence, not freshly measured facts. `make format` rewrites source and the existing shell test launches generation, so neither was run. This is plan-text closure, not implementation certification.

## C9 landing

CLOSED — GPT round-2 B-new-1 / Opus NB-3.

Quoted landed text from `docs/2026-11-14-ltx-wrapper-implementation-plan.md`:

- Line 94: “`POST /interrupt` with JSON **`{"prompt_id": <own_comfy_prompt_id>}`** and Content-Type application/json” and “**Never send an empty-body/global interrupt; never fall back to one** when ownership is absent, changed, or uncheckable.”
- Line 95: “Pending owned prompt: `POST /queue {"delete":[id]}`, then **re-read queue/history** — a 200 does not prove removal, and the prompt may have moved to running; if running, use the same targeted interrupt.”
- Line 96: “the failed job keeps its slot and its input snapshot until the owned prompt is actually absent/terminal AND the executor has quiesced” and “Monotonic failed status; no late output publication.”
- Line 97 lists own-running→other-running, own-pending→own-running, no-op/transport failure, no known prompt id, retained ownership/input, cleanup before handoff, and cancel-while-queued regressions for both wrappers. It explicitly asserts “the exact interrupt JSON, zero global interrupts, no foreign-prompt action.”
- Line 41 applies the same absent/terminal-plus-quiesced condition to input cleanup; line 27 specifies `failed` with error `cancelled`, not a lasting `cancelled` status. Steps 4 and 5 assign lifecycle implementation/tests to both wrappers.

The contract, tests, cleanup rule, and implementation allocation agree. This closes the cancellation amendment at plan level; no unbuilt lifecycle test is reported as executed.

## C10 landing

PARTIAL — Opus round-2 B-new-1 / GPT N-new-1. The environment correction is landed; the preflight scheduling is contradictory.

Quoted landed text:

- Line 17: “create `/home/jarvis/.venv/wan2.2-hg2-tests` with **`/usr/bin/python3.12 -m venv`**, install **pytest only** into it, and add a `.pth` file appending `/home/jarvis/.venv/wan2.2/lib/python3.12/site-packages` **read-only**. **Never install into the shared venv.**”
- Line 17 pins `cd /home/jarvis/Wan2.2-hg2 && WAN_OUTPUT_DIR=<tmp> LTX_OUTPUT_DIR=<tmp> /home/jarvis/.venv/wan2.2-hg2-tests/bin/python -m pytest tests/`, with the worktree root on `sys.path` via pytest configuration or conftest.
- Line 17: “Step 0 runs an import/collection preflight (**both wrappers importable**, env vars set before import)” and records interpreter 3.12.3 plus fastapi/pydantic/httpx versions “**with their import origins**” alongside pytest's version.
- Step 0, line 102 repeats the explicit interpreter, pytest-only installation, read-only shared-package path, preflight, environment variables, and dependency-version/origin recording.

Thus the interpreter, package visibility, shared-venv protection, test command, and provenance requirements are all present. The only missing correction is to schedule the both-wrapper preflight after its code dependencies exist, as detailed below.

## Non-blocker presence

- NB-1 — PRESENT: line 56 requires temporary HOME before imports and a real-home-unchanged assertion; line 66 routes WAN output writes through `config.OUTPUT_DIR`, identifying the legacy home-based output/calibration paths.
- NB-2 — PRESENT: lines 44, 51, and 66 put the shared tail in `local_media.py` for both wrappers, in the executor, with expiry check, atomic rename before completion, and real WAN-path exact-size fixture coverage.
- NB-3 — PRESENT: lines 94–97 contain the targeted-interrupt correction and queue-transition regressions; consolidated as C9 above.
- NB-4 — PRESENT: line 35 places the lock across admission busy-check and slot reservation in `main.py`; `/prompt` occurs in the worker after 202, with later rejection becoming job failure.
- NB-5 — PRESENT: line 35 orders busy/unavailable refusal before staging and requires cleanup/zero-leak tests; lines 41–42 cover terminal cleanup without premature draining-input deletion.
- NB-6 — PRESENT: lines 27, 65, and 97 require monotonic failed/cancelled semantics and cancel-while-queued never being revived.
- NB-7 — PRESENT: lines 56 and 87 list/assert `enable_vae_tiling:false`, `tile_x:272`, `tile_y:272`, `tile_stride_x:144`, `tile_stride_y:128`; Step 5 retains the INPUT_TYPES confirmation.
- NB-8 — PRESENT: line 110 names the still-live-wrapper/direct-ComfyUI measurement paths, daemon-reload, LTX restart implication, and generated-size ≈1504-second estimator label. No measured runtime is claimed by this pass.
- N-new-2 — PRESENT: lines 139–150 retain the former self-approval as superseded history, carry the actual round-2 outcomes and reviewed v1.1 SHA256, and identify the narrow text-check closure gate. The present verdict, not the self-approval label, decides closure of this v1.2 snapshot.

## Amendment-introduced contradictions

### R3-1 — C10 requires a successful both-wrapper preflight before the new wrapper exists

Blocking correction, localized to preflight ordering.

Evidence:

1. §0.7, line 17 explicitly places “both wrappers importable” in **Step 0**; Step 0, line 102 repeats the import/collection preflight.
2. The plan classifies `ltx_service` and the offline test files as **New (peer worktree)**, lines 48–56. The captured peer evidence contains the existing WAN wrapper, not an existing LTX wrapper; the scope also describes LTX as a new package. Local discovery was not substituted for a peer runtime claim.
3. Step 2, line 104 creates LTX config/schemas; Step 3, line 105 creates its graph; Step 4, line 106 creates its worker and `main.py`. Step 1, line 103 creates `local_media.py` and its tests. The planned conftest import/environment setup is also a new file, line 56.

Consequently Step 0 cannot prove both wrapper applications importable or collect their not-yet-created tests. A correct 3.12 interpreter and `.pth` file solve dependency visibility but cannot supply application modules assigned to later steps. Satisfying this gate literally would require advancing implementation ahead of setup/the pre-edit golden, or silently skipping part of a stated gate. This is an executable dependency-order contradiction introduced by C10, not harmless stale labeling or an invitation to redesign the wrappers.

Required minimal amendment:

- Step 0: establish the isolated test environment and safe pre-import environment/import path; verify the runtime dependencies and the existing unmodified WAN code needed for the T2V golden; record the specified versions/origins and capture the golden before edits. Do not require the future LTX app or future tests to exist at this point.
- Run incremental import/collection checks against each step's actual new modules/tests; place the explicit **both-wrapper application import and test-collection preflight after Step 4**, then rerun it after the WAN changes at Step 5 and before the full suite at Step 6. Keep the pinned interpreter/command, temporary HOME, both output-dir variables before imports, and shared-venv read-only rule unchanged.
- Align §0.7, Step 0, and the relevant later step gate. Close that exact amended text; no new design review or change to the earlier CLOSED findings is requested.

No C9-introduced contradiction was found. No other blocking correction is raised in this narrow pass. All requested non-blockers are present; they do not independently hold this verdict open. The corrected environment mechanism itself is accepted.

## Direct answer

v1.2 is not closed and executable unchanged: C9 and the C10 environment mechanism are landed, but move the both-wrapper import/collection gate after creation of the new LTX wrapper and close that exact sequencing amendment before execution, with D1–D4 and J1–J4 unchanged.

<!-- HERMES-CONSENSUS-BRIDGE
run_id: 20261114T143947.513834Z-b9421c4826
status: COMPLETE
decision: REVISE
expected_head: 4b791dbfb940792178b8287fd5501bbf732fe9ae
expected_fingerprint: 4326575a8e7162a18905c1ae2642b5b4bd928979a606b44dbfa0c6d5c2b9de92
input_sha256: 082db99c2f461c025b49576491dba88bc706b918531c9f50217f9a116b94341f
named_sources_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
-->
