# GPT VERDICT — LTX wrapper + WAN upgrade plan (round 2 closure)
Reviewer: GPT/Hermes, gpt-6.1-sol-900k, openai-codex; consensusbridge Round-B seat
Date: 2026-11-14
Sources read:
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round2-FOR-GPT-INPUT.md`.
- `docs/2026-11-14-ltx-wrapper-implementation-plan.md`, complete v1.1.
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round1-CONSENSUS.md`, `2026-11-14-ltx-wrapper-plan-round1-GPT-VERDICT.md`, `2026-11-14-ltx-wrapper-plan-round1-OPUS-VERDICT.md`, and the round-1 input packet.
- `docs/2026-11-14-ltx-wrapper-scope.md`, `docs/2026-11-14-orchestrator-spec-analysis.md`, and its underlying `/home/jose-a-pichardo/Downloads/dual_rtx5060_comfyui_video_orchestrator_spec.md` (context, not an execution instruction).
- Complete frozen copies: `docs/reviews/engine-local-wan.mjs`, `engine-local-ltx.mjs`, `engine-cli.mjs`, `engine-clips.json`, `engine-local-services.json`, and `peer-evidence.md`.
- Local context: `NEXT_SPRINT.md`, `pyproject.toml`, `Makefile`, `tests/README.md`, `tests/test.sh`, `wan/configs/__init__.py`, `wan/configs/wan_ti2v_5B.py`.
- Fresh read-only peer SSH: WAN config/schema/main, worker hash versus captured source; both systemd units and WAN effective paths; ComfyUI `nodes.py`, `server.py`, `execution.py`, WanVideoWrapper `nodes.py`, relevant `nodes_sampler.py` sections, the shipped 5B I2V workflow, LTX node definitions, Q3 runbook, calibration, and interpreter/package discovery.
- Supplemental local Locksmith tree: frozen commit `4d4e4fa` versions of the three supplied engine modules; targeted `jobs.mjs` polling/constants and `core/download.mjs` signature/bound implementation. No engine execution or writes.

## Verdict
REVISE BEFORE EXECUTION

Decision: REVISE

The revised mapping, graph topology, worktree isolation, synchronous admission requirements, and deadline/publication invariants substantially close round 1. One bounded safety correction remains: the own-prompt preflight before `/interrupt` does not prevent interruption of another wrapper's prompt after the queue changes. The live ComfyUI server already supports a prompt-targeted interrupt body. Specify and test that existing API rather than retaining the check-then-global-interrupt pattern. See B-new-1.

This is a GPT/Hermes closure vote, not a claim of completed cross-family consensus on v1.1. The supplied Opus round-1 report was read in full; no live Opus/Claude round-2 reviewer was invoked or impersonated. No final-round disagreement matrix or tie-break trigger is asserted. J1–J4 remain operator gates, not newly imposed plan blockers.

### Pinned-state receipts

Repository root, branch and HEAD were verified first. Before substantive judgment, the bridge's read-only `repo_snapshot` function reproduced all supplied pins; the same checks passed again after evidence gathering and before writing:

- Root: `/home/jose-a-pichardo/Wan2.2`.
- Branch: `main`.
- HEAD: `4b791dbfb940792178b8287fd5501bbf732fe9ae`.
- Worktree fingerprint, excluding the protocol input/output as the bridge does: `e9be8e1541284d229acf200ae47b39faf65df8174a5de6b2b52712e6450b324d`.
- Input SHA256: `64660fe84a3e4e776f465ad4f3fb459140132c406288668782afa3f29f67927c`.
- Named ignored-source manifest SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. This is an empty ignored-source manifest, not an assertion that the review has no named sources. The ordinary untracked evidence is covered by the worktree fingerprint.
- Reviewed plan SHA256: `3709ba4ceacd406c5ba41b81483938ddc5b1c9c5224b0a3bc0e2218b974c3fee`.
- Peer-evidence SHA256: `fe1227ee98f5c538e6bba8461c6af36e7e2d846328f13ff5ad63bd7460cc23d9`.
- Origin divergence, without fetching: 3 ahead / 0 behind. The tracker explicitly labels its older two-commit measurement as historical; it is not a current-state pin.
- Peer WAN stayed clean on `main` at `3a4b80b5943ec6bb52615196c91618e8769b6971`. The important peer server/node/worker hashes were unchanged on the closing read.

## Prior finding closure audit

CLOSED means the requested correction is present in this implementation plan, not that unbuilt code or future tests have already passed. PARTIAL means a material remainder exists. References below use v1.1 section and local plan line numbers; original numbering is preserved separately for each seat and for the consolidation.

| Prior finding | Status | Evidence | Residual risk |
|---|---|---|---|
| GPT B1 — admission before 202 | CLOSED | §2, lines 35–42: admission is “BEFORE the 202 and before any queueing”; HTTP tests require “zero ComfyUI prompt submissions on any refusal.” §3 moves WAN checks before `pool.submit`. | Implementation must actually exercise both wrappers through HTTP, not just helper tests. Later background failures are explicitly job failures. |
| GPT B2 — stills snapshot integrity | CLOSED | §2, lines 38–42: containment, regular file, “refuse symlink escapes at every component,” read once, hash/write “those same bytes,” exclusive destination, deterministic replacement and destination-hash tests. | Implement the stated no-escape invariant with race-resistant opening, including ancestor changes; a pathname precheck alone is not equivalent. No helper implementation exists yet. |
| GPT B3 — timeout state reversal | PARTIAL | §5, lines 93–95: failed “forever,” no late publication, draining ownership, and late-success/error regressions. These close the demonstrated state-reversal design defect. | The added cancellation remedy still permits a stale preflight followed by global interruption; B-new-1. |
| GPT N1 — advisory interlock | CLOSED | §5, line 96 explicitly says “advisory,” retains ComfyUI serialization and sequential live policy; §3, lines 50–54 adds depth 1, lock and simultaneous-admission tests. | No cross-wrapper atomic exclusion is claimed. Local admission must reserve its slot, rather than only lock an enqueue operation. |
| GPT N2 — T2V identity and guidance/fps | CLOSED | §3, line 64 narrows identity to “704×1280 default shape with default cfg,” wires guidance for “T2V and I2V,” and documents fps 24. Step 0 captures a fixed-seed pre-edit golden. | Intentional non-default CFG differences must not be hidden by the golden. |
| GPT N3 — fixed clips and measured timeout | CLOSED | Step 8, line 108 specifies measurement, ≥2× measured/extrapolated HG-2 time, drop-in, confirmed restart and effective-env verification; §1, line 31 records engine budgets; J3/J4 retain tag/approval gates. | Extrapolation is not a measurement of the final job. See arithmetic receipts below. |
| GPT N4 — graph/smoke/media assertions | CLOSED | §4, lines 72–82: round-up/no padding, audio/video frame and fps wiring, one reused random seed, node 31, per-job prefix; §3, line 54 adds prompt-object golden, pinned fixture and actual ffmpeg fixture test. Step 7 says “final-request 1280×720.” | Frame-snap tie/minimum behavior must be explicit in the implementation's tests, as required by line 73. |
| GPT N5 — deployment/evidence boundaries | CLOSED | §0, lines 13–18: restart gate, network-policy verification, separate test environment, no pushes. §1, line 30 unifies variant defaults; Step 6 records actual version/counts. | Scope/tracker historical examples do not override v1.1. No inherited 571-test total is accepted as a newly verified result. |
| Opus B1 — invalid WAN 720 dimension | CLOSED | §4b, line 86: “1280×736” then crop 8 per side, “Never pad”; same I2V resize dimensions. Step 8 requests 1280×720. §3 narrows golden identity. | Structural grid fix verified; no new GPU render was performed. |
| Opus B2 — wrong WAN I2V topology | CLOSED | §4b, line 87 replaces the channel-concat encoder with `ImageScale` → `WanVideoEncode` → `WanVideoEmptyEmbeds(extra_latents)` → sampler. Fresh peer schema and sampler reads confirm these ports/types. | Populate all required encoder scalar inputs at Step 5; the plan expressly retains INPUT_TYPES discovery and visual fidelity gate. |
| Opus B3 — LTX round-down/black padding | CLOSED | §4, line 72: “rounded UP,” 640×384 → 1280×768 → crop 24 rows/side; “Never pad.” Golden and 1080 runbook arithmetic both reproduce. | None at the mapping-design level. |
| Opus B4 — timeout budget and orphaned prompts | PARTIAL | Step 8 closes part (a)'s measured configuration gate. §5 closes part (b)'s monotonic state/draining requirements and calls for “orphan cleanup.” | Cancellation ownership across queue transitions is not yet safe; B-new-1. |
| Opus B5 — live-tree build/restart/rollback | CLOSED | §0.4, line 14 and Step 0: separate worktree; “live tree ... stays on main”; LTX points at worktree; WAN moves only at Step 8. Fresh unit reads confirm why this isolation is needed. | Installation/fast-forward/restart remain owner-controlled. No worktree or branch was created by this review. |
| Opus N1 — reciprocal check/lock/depth/GPU setting | CLOSED | §3, lines 50–54: depth 1, `asyncio.Lock`, simultaneous-admission tests; modified WAN worker adds busy check. §5/Step 8 set `WAN_GPU_IDS=0` and label interlock advisory. | Not a distributed lease; intentional. |
| Opus N2 — WAN validation placement | CLOSED | §2, line 35 and §3, line 63: stills/variant/busy checks in `main.py` “before `pool.submit`,” with HTTP tests for both services. | Requires implementation proof, not another plan loop. |
| Opus N3 — variant defaults disagree | CLOSED | §1, line 30: “One setting drives schema default, validation and /health”; omitted variants and bare request regression are specified; §4b repeats bare-T2V coverage. | Jose's existing registry still needs J3, as already acknowledged. |
| Opus N4 — 422/list detail and ComfyUI 400 | CLOSED | §1, line 25 overrides `RequestValidationError` with 400/string fields. §2, line 35 distinguishes definite `/prompt` rejection from connection failure and explicitly says later background failures cannot change the original POST. | A ComfyUI 400 arising only after 202 is a failed job, not a retrospective HTTP 400. The new explicit boundary controls that shorthand. |
| Opus N5 — complete LTX parameter coverage | CLOSED | §4, lines 73–80 names nodes 8/9, 5/9/19, 31, both noise nodes; §3, line 54 requires prompt-object comparison and SHA-pinned fixture. | Graph/mapping tests must vary those fields, rather than only compare the pilot default. |
| Opus N6 — stills guard details | CLOSED | §2, lines 38–42 explicitly includes containment, regular file, sanitized basename, relative join, exact bytes, exclusive write, cleanup and LTX-required image. | Logical failure must not trigger premature input deletion while a prompt is still draining; include that in B-new-1's lifecycle tests. |
| Opus N7 — isolated test venv/setup order | CLOSED | §0.7, line 17 and Step 0 create the test environment before Step 1, leave the generator venv unchanged, and set output dirs before import. | Exact interpreter/dependency provenance should be pinned during setup; N-new-1. |
| Opus N8 — pre-edit deterministic T2V golden | CLOSED | §3, line 64 and Step 0 require “unmodified 3a4b80b,” fixed seed and capture before edits. | Do not regenerate the expected golden from changed code. |
| Opus N9 — responsiveness/atomic publication/audio | CLOSED | §3, line 52: executor for blocking work, ffmpeg then “atomic rename ... completed only after”; §4 specifies `-c:a copy`; §5 prohibits expired-job publication. | The promised fixture tests must test real media, not arithmetic alone. |
| Opus N10 — LTX unit user and import roots | CLOSED | §3, line 56: `User=jarvis`, worktree WorkingDirectory/PYTHONPATH, shared runtime uvicorn and one worker. Existing WAN unit uses the analogous main-tree root. | Both packages must import root-level `local_media` using their actual service roots; no implementation import was claimed verified. |
| Opus N11 — portrait/possibly wrong still | CLOSED | J1, line 125 preserves subject review, portrait dimensions and re-stage/hash requirement. Recomputed retained height fraction is 31.657%. | Explicit operator visual gate; not a plan blocker. |
| Opus N12 — GPU1 fault | CLOSED | J2 and Step 7 put hardware check before live smoke; §5/Step 8 choose single WAN worker GPU id 0. | Hardware clearance remains Jose's; no new GPU-health assertion is made. |
| C1 — admission boundary | CLOSED | §2, line 35: synchronous ordered acceptance plus HTTP refusal tests with zero submissions; §3 assigns WAN route changes. | Endpoint implementation/tests are future deliverables. |
| C2 — immutable accepted still | CLOSED | §2, lines 38–42: no symlink escape, exact accepted bytes, exclusive unique destination, cleanup and deterministic replacement tests. | Preserve the full no-escape requirement when selecting the opening technique. |
| C3 — terminal lifecycle and owned cancellation | PARTIAL | §5, lines 93–95 correctly states monotonic failure and draining, but uses `/queue` preflight then `/interrupt`, describing interrupt as global. | Fresh live-code counterexample and exact required amendment in B-new-1. |
| C4 — WAN generated/output dimensions | CLOSED | §4b plus Steps 5/8: /32 round-up, same still resize, exact crop, real HG-2 request shape in smoke. | No black-padding branch is retained. |
| C5 — 5B extra-latents chain | CLOSED | §4b, line 87 matches fresh `WanVideoEmptyEmbeds` and sampler source; core ImageScale is present with lanczos/center. | WIP example is structural evidence, not visual proof; planned live gate remains appropriate. |
| C6 — LTX round-up without padding | CLOSED | §4 and Step 7 produce 1280×720 by crop and reproduce the golden/runbook dimensions; independently recalculated below. | No mapping contradiction remains. |
| C7 — measured timeout installation gate | CLOSED | Step 8 requires ≥2× landscape-derived budget, per-service env, confirmed restart and effective-env check; §1 gives engine poll/failure/stale budgets. | Measured values and J4 approval are intentionally not invented here. |
| C8 — isolated worktree deployment | CLOSED | §0.4 and Steps 0/8 keep main unmodified until owner deployment and LTX on its own worktree. Actual unit roots verified over SSH. | Independent rollback design is preserved. |

Closure tally: 33 original numbered entries reviewed; 30 CLOSED, 3 PARTIAL, 0 NOT ADDRESSED. The three PARTIAL entries are overlapping references to the same residual cancellation-safety issue, not three independent blockers.

## New-blocker pass

### Checks performed and results

1. **Contract and health-gate execution — PASS with injected dependencies.** Freshly evaluated the actual supplied adapter and `localTestHandler` function bodies in Node, replacing unavailable surrounding dependencies with explicitly fake transport/ledger/filesystem hooks. Health 200 → true; health 429/503 → false. Submit 202 → created, 400 → failed, 429/503 → uncertain. Poll `failed` → failed, `cancelled` → poll_failure. Null seed, no Authorization and redirect rejection assertions passed. For an unhealthy route, the actual CLI handler refused with `local_service_unavailable` and zero ledger/state hook touches. This validates the proposed health interlock's engine-side effect, not an unimplemented wrapper health route. The initial probe had a harness syntax error; the corrected probe completed successfully. No product service or real ledger was called.

2. **Frozen-source authenticity — PASS.** All three supplied `.mjs` files compare byte-for-byte with `git show 4d4e4fa:scripts/ads/lib/...` in the Locksmith repository. That repository's current HEAD is `6ede583d793fb1edfb945b2f0e5cda88ea1eb3b5`; this was not substituted for the plan's frozen source. Targeted polling code confirms pending responses continue polling and failures become uncertain at the stated threshold. Download source confirms the 250 MiB cap and `ftyp` check; no download/generation was performed.

3. **Recomputed graph and clip tallies — PASS.** Parsed the captured Q3 prompt map: 31 nodes, 41 links, zero dangling references, 8 and 3 sigma intervals. The frozen set contains one clip, 1280×720, 97 frames, 24 fps, 50 steps, CFG 5, seed 1. The captured WAN modules contain 16 + 57 + 96 + 447 = 616 source lines; all four reconstructed module hashes match the live peer. v1.1 names ten proposed `test_*.py` modules plus `conftest.py`; these are creation tasks, not pre-existing passing tests. The local checkout has zero Python test modules under `tests`, no wrapper packages, no root AGENTS/CLAUDE/cursorrules file and no workflow files under `.github/workflows`. The existing shell test runs GPUs and the Makefile format target rewrites source; neither was run.

4. **Mapping arithmetic — PASS.** Computed, rather than inherited:

   | Route/request | Base/generated dimensions | Exact output operation |
   |---|---|---|
   | LTX 1280×720 | half-resolution round-up to /32: 640×384; ×2 → 1280×768 | crop 24 rows per side |
   | LTX golden 1088×1920 | 544×960; ×2 → 1088×1920 | no crop/pad |
   | LTX runbook 1080×1920 | 544×960; ×2 → 1088×1920 | crop 4 columns per side |
   | WAN 1280×720 | /32 round-up → 1280×736 | crop 8 rows per side |
   | WAN legacy 704×1280 | unchanged | no crop/pad |

   LTX formulas are `base_w = 32 * ceil(request_w / 64)` and the same for height. WAN uses `32 * ceil(request_dim / 32)`. Neither needs padding. LTX stage-2 pixel increase versus the former 1280×704 design is 9.0909%. The fixed 97-frame request satisfies both models' temporal grids.

5. **WAN node contracts — PASS at the design level.** Fresh peer `nodes.py:1892–1922` exposes core ImageScale inputs `image`, `upscale_method`, `width`, `height`, `crop`, including lanczos/center and IMAGE output. WanVideoWrapper `nodes.py:1411–1446` accepts LATENT `extra_latents`, places its samples at index 0, and returns WANVIDIMAGE_EMBEDS. `nodes.py:2234–2292` exposes WanVideoEncode's required `vae`, `image`, `enable_vae_tiling`, `tile_x`, `tile_y`, `tile_stride_x`, `tile_stride_y` and LATENT output. Step 5 must populate those required scalar inputs; the shipped example uses false/272/272/144/128. Sampler `nodes_sampler.py:112–113,336–340,753–775,1824+` verifies the 5B branch and extra-latent insertion. The shipped WIP workflow has that same chain. This is not a claim that any sampler/scheduler combination has now been rendered successfully.

6. **LTX node/grid and fixture provenance — PASS.** Fresh `comfy_extras/nodes_lt.py:63–84,152–166` verifies /32 spatial controls, temporal step 8 and center-crop still preprocessing. The runbook confirms 544×960 → 1088×1920 and the 4-column crop. Step 0 correctly pins the actual JSON before builder development; tests compare its prompt map, not the client envelope.

7. **Setup/deployment/publication ordering — PASS with the named non-blocking setup clarification below.** Step 0 precedes all golden/venv consumers. Existing WAN WorkingDirectory and PYTHONPATH both point at `/home/jarvis/Wan2.2`, with Restart=on-failure; the separate worktree is therefore necessary and correctly specified. LTX's proposed root supports a root-level shared module; WAN's main-tree root will also contain it after deployment. Actual imports cannot be tested before those files exist. Environment drop-ins are compatible with the present unit; current WAN DropInPaths is empty. Installation must load the unit changes and verify effective per-service values, as Step 8 requires. LTX ffmpeg → atomic rename → completed is explicit, and both wrappers must reject late publication under §5. These are future acceptance tests, not checks falsely reported green now.

8. **Timeout arithmetic — PASS as an explicitly approximate gate.** Fresh calibration is `3.2485627610844007e-7` seconds/unit. For the frozen request, workload multiplication gives 1452.0296 seconds; adding the captured estimator's 20-second term gives 1472.0296 seconds. Thus the plan's approximately 1472 seconds is reproducible as an estimator, not a measured duration. At the corrected generated 1280×736 shape the analogous estimate is 1504.2969 seconds including overhead. Step 8's measured landscape run and ≥2× budget remain the controlling acceptance, not either extrapolation. No hardware clearance or final timeout approval was manufactured.

9. **Queue-delete/interrupt API — shape confirmed; ownership gap found.** Peer `server.py:1243–1254` accepts `{"delete":[id]}` and returns 200 even when no queue item matched. `execution.py:1405–1416` only removes pending entries. A pending prompt can become running between preflight and deletion. More importantly, `server.py:1257–1286` already supports `{"prompt_id": id}` for targeted interruption; omission of that field is the global branch. The existing captured WAN client's `interrupt()` sends an empty body (`peer-evidence.md:337–343`). See B-new-1.

### B-new-1 — Own-prompt preflight is not a safe substitute for targeted cancellation

**Claim →** v1.1 §5, lines 93–95 promises draining ownership, orphan cleanup and “Never blind-interrupt,” but specifies a `/queue` ownership check followed by `POST /interrupt`, describing the latter as global. It does not require the live server's prompt-targeted request body or the queue-transition regressions necessary for this invariant. Reusing WAN's existing empty-body `interrupt()` follows that outline and is unsafe.

**Evidence →** The ownership check and the global interrupt are separate network requests. Between them, the owned prompt can finish and another wrapper's admitted prompt can start. Both the advisory interlock and ComfyUI serialization expressly permit this situation. A local asyncio lock cannot protect another service's queue advancement.

Fresh peer `server.py:1263–1284` shows the existing distinction:

- With `prompt_id`, the handler checks that id against running entries and skips interruption if it is absent.
- Without `prompt_id`, it calls the global interruption function unconditionally.

I extracted and executed that actual `post_interrupt` AST function with an in-memory fake queue, fake request and fake interruption recorder. No HTTP POST or live interruption was sent. With an earlier own-prompt preflight assumed and the queue now running the other wrapper's prompt:

| Request body delivered to actual handler body | Recorded effect |
|---|---|
| `{}` — existing client's behavior | `INTERRUPTED_OTHER_PROMPT` |
| `{"prompt_id":"own-prompt"}` | no interruption |

The peer server source hash is `6e3614c753c95b037e57e25dfc2de979de70136baad2a3abb5d2d32aaf05281e`, unchanged on the closing read. This is a deterministic safety counterexample to the proposed preflight-based remedy, not an allegation that a foreign live job was interrupted during review.

**Why blocking →** This crosses the explicitly protected other-wrapper/resource-ownership boundary. Sequential owner use mitigates frequency but does not establish the promised invariant; cancellation/late-result handling exists precisely to handle abnormal transitions. It also leaves the pending→running case under-specified: queue-delete 200 is not proof that the owned prompt was removed.

**Required amendment →** In both wrappers, make cancellation prompt-targeted: `POST /interrupt` with JSON `{"prompt_id": owned_comfy_prompt_id}` and Content-Type application/json. Never fall back to empty-body/global interrupt if ownership is absent, has changed, or cannot be checked. Delete a pending owned prompt by id, then re-read queue/history: if it moved to running, use the same targeted interrupt. Keep the failed job draining and its necessary input snapshot retained until that owned prompt is actually absent/terminal and its executor has quiesced; a deletion/interrupt HTTP 200 alone does not free the slot. Preserve monotonic failed status and prevent late output publication.

Extend the already-planned fake lifecycle tests for both wrappers with these deterministic cases: own-running→other-running between check and action; own-pending→own-running before delete; delete/interrupt no-op or transport failure; no known prompt id. Assert the exact interrupt JSON, zero global interrupts, no foreign-prompt action, retained ownership/input while draining, and eventual own-prompt cleanup before next-job handoff. This is a small amendment to the existing lifecycle work, not a distributed scheduler or any ComfyUI modification.

## Non-blockers

### N-new-1 — Pin the test interpreter and record dependency origins, not only pytest

The separate test venv is the right isolation boundary, but `--system-site-packages` does not mean “inherit the ComfyUI venv.” Fresh peer discovery found default `/usr/bin/python3` is Python 3.14 and cannot discover fastapi, pydantic, httpx or uvicorn. The generator venv is Python 3.12.3. `/usr/bin/python3.12` successfully imports FastAPI 0.129.0/httpx 0.28.1/Pydantic 2.12.5 from Jarvis's user site, whereas the generator venv has its own package copies. Therefore an assertion that no usable base dependencies exist would be false; a Python-3.12-based test environment can be viable.

Specify the interpreter explicitly in Step 0 and record import origins/versions for FastAPI, Pydantic and httpx alongside pytest. If chosen dependencies are absent, install only into the isolated test environment, never into the live generator venv. Add the intended worktree root to test import configuration and run the import/collection preflight with both output-dir env variables already set. This is a reproducibility improvement to a setup step, not a demand to change the served runtime or a demonstrated product defect. One introspection probe could not obtain frozen `site.venv` source through `inspect`; reading the interpreter's source file and explicit module import checks supplied the evidence instead.

### N-new-2 — Treat the provenance self-approval as history, not closure evidence

Plan line 148 says post-apply “APPROVED” while the document header describes an amended snapshot awaiting closure. That approval label cannot override this independent exact-snapshot review. It is non-normative provenance prose, so it is not another blocker. Carry the actual closure result and reviewed hash forward when the lifecycle amendment is applied; an amended normative snapshot needs its own exact-snapshot closure.

## Direct answer

v1.1 is substantially improved but is not executable unchanged under its own cancellation-safety promise. Its admission design, exact-size mappings, 5B extra-latents topology, isolated worktree, golden setup and owner-controlled live gates are aligned with the inspected sources. Amend the single lifecycle ownership issue in B-new-1, then close that amended snapshot before building; do not reopen D1–D4 or recast J1–J4 as plan blockers. This pass reproduced the pins, all 33 prior finding dispositions, graph/clip/test tallies, mapping/timeout arithmetic, real adapter/health-gate behavior and a real-handler cancellation counterexample. It did not run an unbuilt wrapper suite, GPU render, upstream 571-test suite, service restart, installation, database test, commit or push. Only this verdict file was written in the repository.

<!-- HERMES-CONSENSUS-BRIDGE
run_id: 20261114T142444.985947Z-9a99c4d730
status: COMPLETE
decision: REVISE
expected_head: 4b791dbfb940792178b8287fd5501bbf732fe9ae
expected_fingerprint: e9be8e1541284d229acf200ae47b39faf65df8174a5de6b2b52712e6450b324d
input_sha256: 64660fe84a3e4e776f465ad4f3fb459140132c406288668782afa3f29f67927c
named_sources_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
-->
