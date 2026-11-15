# GPT VERDICT — LTX wrapper + WAN upgrade plan (round 1)
Reviewer: GPT/Hermes, gpt-6.1-sol-900k, openai-codex; consensusbridge Round-B seat
Date: 2026-11-14
Sources read:
- Project root: `/home/jose-a-pichardo/Wan2.2`.
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round1-FOR-GPT-INPUT.md`.
- `docs/2026-11-14-ltx-wrapper-implementation-plan.md` — complete source plan.
- `docs/2026-11-14-ltx-wrapper-scope.md`.
- `docs/2026-11-14-orchestrator-spec-analysis.md`.
- `docs/reviews/engine-local-wan.mjs`.
- `docs/reviews/engine-local-ltx.mjs`.
- `docs/reviews/engine-cli.mjs`.
- `docs/reviews/engine-local-services.json`.
- `docs/reviews/engine-clips.json`.
- `docs/reviews/peer-evidence.md` — complete captured WAN modules, Q3 graph, and peer facts.
- Local project context: `NEXT_SPRINT.md`, `pyproject.toml`, `Makefile`, `tests/README.md`, `tests/test.sh`.

## Verdict
REVISE BEFORE EXECUTION

Decision: REVISE

The chosen topology and scope are sound. Preserve D1–D4, the frozen engine, shared ComfyUI, Q3, operator-owned live runs, and restart gates. Amend the admission boundary, stills snapshot integrity, and retained WAN timeout behavior before implementation. These are bounded correctness fixes, not a request for a durable store, a second generator, or orchestration infrastructure.

This is the GPT/Hermes bridge vote, not a completed bilateral consensus. No separate Opus findings or endpoint result was supplied or invoked in this bounded pass. The source packet's independent-review instructions do not themselves establish another model's agreement. No final-round disagreement or tie-break request is asserted.

## Live-code spot-check lens (mandatory)

### Pinned state and provenance

Before substantive review, `pwd`, `git rev-parse --show-toplevel`, branch, HEAD, and status confirmed the requested repository on `main` at `4b791dbfb940792178b8287fd5501bbf732fe9ae`. The bridge's read-only `--print-pin` reproduced:

- Worktree fingerprint: `a36a74461b6ec76b7cd258f83a08ab85e379b72a2c190e1d0a90246c8b25fd4c`.
- Named ignored-source manifest: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Independently hashed input: `a0e7547d8cd9bc74cf42b84b90aa87af02d7e485431fb849f7e611186f70ae29`.

The empty named-source manifest is not an assertion that no sources were read; ordinary untracked sources are covered by the worktree fingerprint. The same pins and input hash were reproduced after the evidence probes and before writing this verdict. The tracked/index diffs were empty; the initial worktree had 10 normal untracked files. Origin divergence reproduced as 3 ahead / 0 behind, without fetching. `NEXT_SPRINT.md:11` explicitly describes an older, pre-correction two-commit measurement; its provider-wiring context is also historical, not authority over the supplied engine copies.

Additional source receipts:

- Plan SHA256: `92e84c5d75aa480ace1d55e53ca1974923d1a3887634d371151d482e33803d6d`.
- Peer evidence SHA256: `fe1227ee98f5c538e6bba8461c6af36e7e2d846328f13ff5ad63bd7460cc23d9`.
- Shared adapter SHA256: `fe7fec3af9f0981c9b2902f0cefeef325ff0141a287401a308610e901ebf6ff7`.

### Contract/data/API lens

Freshly read the shared adapter and exercised its actual function bodies in Node with an injected, in-memory transport. Imports unavailable in the packet were replaced with explicitly labeled stubs; download helpers were not exercised. Assertions passed for the exact POST field set, `seed: null` preservation, no Authorization header, and redirect rejection. Observed submit results:

| Response | Adapter outcome |
|---|---|
| 202, valid `gen-a_b-1` ID | created |
| 202, invalid `bad/id` ID | uncertain |
| 400, string error | failed, with that error |
| 422, array detail | failed, generic `local_provider_failed` |
| 429 | uncertain |
| 503 | uncertain |

Poll probes confirmed queued/processing → pending, completed → zero-cost `provider_reported` with the selected provider tag, failed → failed, 404 → not_found, and **cancelled → poll_failure**. See `engine-local-wan.mjs:107–172`. Thus pre-202 rejection versus post-202 asynchronous failure is consequential, not cosmetic; see B1.

`engine-local-ltx.mjs:5–18` genuinely delegates to the same factory. `engine-cli.mjs:690–800` confirms dry runs do not call health; execute performs health gating, local-owner purity checks, zero-cent budgeting, all-zero still-hash refusal, and seed-changing bounded retry planning. The CLI does not expose frame/size/step overrides. Its local recovery delegates to `reconcile`, whose implementation is not in this packet.

Both model fields need the already-planned owner change: copied registry values are `wan2.2-14b-fp8` and `ltx-2.5`, not `5b-gguf` and `ltx-2.5-q3`. This is an explicit prerequisite already identified by the plan, not a newly discovered blocker.

### Graph/media lens

Parsed the actual Q3 JSON from `peer-evidence.md:627–989`: **31 nodes, 41 input links, no dangling node references**. IDs are intentionally non-contiguous. Confirmed:

- Video latent node 8 and audio latent node 9 both use 121 pilot frames.
- Conditioning node 5, audio node 9, and CreateVideo node 19 all carry frame-rate inputs.
- I2V nodes 33/34 use strengths 0.7/1.0 and the preprocessed image from node 32; node 31 supplies the ComfyUI input filename.
- Upsample/AV separation and recombination links agree with the proposed two-stage builder.
- Both noise nodes use seed 42 in the pilot; guider video/audio CFG are 1.0.
- Sigma lists recompute to 8 and 3 steps; tiled decode is 256/64 spatial and 64/16 temporal. Audio reaches CreateVideo; SaveVideo uses h264 and `format: auto`.

Recomputed final-request mapping: 1280×720 → stage 640×352 → upsample 1280×704 → **pad**, not crop alone, to 1280×720. A final 1088×1920 request reproduces the pilot's 544×960 stage. Frames 17, 33, 97, and 121 all satisfy 8k+1. The fixed engine file contains **one clip**, at 1280×720, 97 frames, 24 fps, 50 steps, CFG 5, seed 1.

Extracted and executed only the pure captured WAN builder via Python AST, without importing configuration or starting workers: it returns **9 T2V nodes**, hardcodes sampler CFG 5.0 and CreateVideo fps 24.0, and has no image-loading path. Its signature accepts neither image nor guidance/fps arguments (`peer-evidence.md:346–440`); the worker call likewise omits them (`521–531`). The stated stills and guidance gaps are real. Actual I2V node INPUT_TYPES/return slots are not captured; Step 5 already makes their peer inspection and any necessary amendment a prerequisite. That explicit discovery gate is appropriate, not an invented schema blocker.

### Planning/test/runtime lens

The new-file table represents **16 files in 15 rows**, including six proposed Python test files; four existing peer files are modified. None of the wrapper packages or proposed tests exists in this local checkout, as expected from the disclosed divergence. Local tracked tests are the GPU-driven `tests/test.sh` and its README, not an existing offline wrapper suite; no tracked GitHub workflows were found. The supplied WAN module bodies total **616 lines**, rather than the scope's approximate “700 lines”; this has no execution consequence.

The claimed 571/571 upstream offline tests, CI result, 250 MiB limit, and `ftyp` implementation cannot be independently reproduced from these copies: upstream tests, `core/download.mjs`, and lifecycle/recovery dependencies are absent. The adapter does invoke bounded-download/signature helpers, but that call site alone does not prove their implementations. The peer source, services, hashes, model inventory, and runbook measurements were reviewed as **captured evidence**, not a fresh SSH/GPU verification.

Read-only probes passed for the contract and graph checks above. A separate isolated probe of the captured WAN process-loop method **reproduced a timeout state reversal**; see B3. No product suite, GPU generation, service change, installation, or shared-database test was run. `make format` was intentionally not run because it rewrites source. Pytest is a local dev extra (`pyproject.toml:33–41`), but peer installation/discovery still needs the plan's explicit venv step.

## Blockers (B1, B2, ...)

### B1 — Make admission-time errors reachable before 202, with HTTP-level tests

**Claim →** Plan `:34–46,53–56,81–82` places stills/variant checks in worker-side work while promising HTTP 400 for stills/validation, 429 for a busy ComfyUI, and 503 for submit unavailability. It does not specify the boundary between synchronous admission and background generation.

**Evidence →** The existing WAN route returns 202 after `pool.submit` (`peer-evidence.md:119–132`). That submit merely enqueues and records a job (`579–616`); workflow building and ComfyUI submission happen afterward (`521–533`). Following this existing pattern with new checks immediately before graph building cannot produce an HTTP rejection for the original POST. The adapter distinguishes definite 4xx from uncertain 429/503 and only obtains a usable job ID from a valid 202 (`engine-local-wan.mjs:136–144`).

**Why blocking →** The central promised refusal contract can otherwise be implemented as “202, then failed,” with the advertised HTTP error mapping unreachable. This is an admission-order ambiguity in a plan, not a claim that unimplemented LTX code already fails open.

**Required amendment →** Define `submit/admit` explicitly: schema and served-variant checks, still preparation/hash acceptance, and any promised busy/unavailable rejection occur before returning 202 and before queueing GPU work. Background generation consumes the admitted snapshot. If ComfyUI submission is intentionally deferred, distinguish an admission-time connectivity failure from a later job failure; do not promise a later failure as the original POST's 503. Add socket-free ASGI endpoint tests for both services proving exact 400/429/503 behavior, zero ComfyUI prompt submissions on refusal, valid 202 IDs, and subsequent status/output/404 behavior. Keep the existing engine unchanged.

### B2 — Hash the immutable staged bytes, not a pathname that is reopened for copying

**Claim →** Plan `:34,41,71` specifies resolve/containment → SHA comparison → copy to ComfyUI input, but no check/use binding.

**Evidence →** The request's only image identity is path plus SHA (`engine-local-wan.mjs:49–67,115–129`), and the graph subsequently reads a separate ComfyUI input filename (`peer-evidence.md:934–948`). `Path.resolve()` followed by a later copy does not ensure the copied bytes are those hashed: content or path components can change between those operations. The listed tests cover static escape/mismatch cases, not that transition.

**Why blocking →** The promised “missing/mismatched still refused” invariant is not guaranteed for the file actually used by generation. This is a missing design guarantee, not evidence of an exploit in nonexistent `local_media.py`.

**Required amendment →** Specify a contained, regular-file snapshot with no unchecked path reopen: use a verified descriptor/bounded snapshot or equivalent race-resistant read, stage privately with a unique exclusive destination, hash the exact staged bytes, and publish the final ComfyUI filename only after acceptance. Address ancestor/final-component symlink substitution as well as static containment; never follow a pre-existing destination link. On failure remove temporary material and submit no graph. Add deterministic replacement/content-change tests between path validation and staging, exact destination-byte/hash assertions, and independent same-basename jobs. A small helper is sufficient; no storage framework is needed.

### B3 — Retained WAN timeouts can change failed jobs back to completed

**Claim →** Plan `:55,85,90–94` retains the WAN worker lifecycle, relies on its timeout, and treats in-memory failure/recovery as an acceptable test-stage limitation. It also proposes reusing worker patterns for LTX (`:39`).

**Evidence →** The captured WAN loop wraps `run_in_executor` in `asyncio.wait_for`, sets `failed/generation_timeout` on expiry, and clears busy/current-job state (`peer-evidence.md:457–479`). Cancellation of that await does not stop the executor thread. The continuing generation routine later writes output and unconditionally assigns `completed` (`549–567`). An isolated execution of the **actual captured `_process_loop` method**, with a 0.01-second deadline and a finite synthetic generation function, observed:

- after the deadline: `failed`, `generation_timeout`, worker busy false;
- after the executor returned: `completed`, still carrying `generation_timeout`.

The probe used no GPU, sockets, database, or filesystem writes. The stub supplied only the late completion; the deadline handling was the captured method itself.

**Why blocking →** This is a confirmed pre-existing defect on the path being upgraded, not merely a hypothetical LTX risk. A terminal failure can reverse after the engine has acted on it, and worker availability can be reported before the underlying operation has ended. Raising a timeout makes this less frequent but does not establish correct deadline semantics.

**Required amendment →** Add a bounded worker-lifecycle correction to Step 5 and require the same invariant for new LTX work: late executor results cannot publish success/output for an expired job, terminal states remain terminal, and resource ownership is not released as though active generation stopped. If generation cannot be safely cancelled, keep it tracked as draining and continue reporting the job failed. Do not solve this by blindly sending ComfyUI's global `/interrupt`, which could interrupt another wrapper's job. Add fake-only regressions for timeout followed by late success/error, terminal-state monotonicity, resource ownership, and handoff to the next job.

## Non-blockers (N1, N2, ...)

### N1 — The `/queue` interlock is advisory, not mutual exclusion

Plan `:39,46,93` and scope `:50–55` overstate the protection. Two clients can both see an empty queue before either POST; existing WAN has two queue workers against the same ComfyUI (`peer-evidence.md:443–449,599–615`) and no reciprocal check. A check performed only inside an accepted background job also cannot return the original POST's 429; that part is covered by B1.

For this scoped test stage, ComfyUI still provides one serial generator and Jose's sequential route policy remains a valid mitigation. Do not add a distributed scheduler merely to satisfy this review. Label the preflight advisory, test simultaneous admissions, and make exclusive/sequential live use explicit. Add a shared admission lease only if strict cross-wrapper exclusion is actually required. No second-generator violation was demonstrated.

### N2 — Narrow “T2V byte-identical” to the legacy/default behavior

Plan `:45,55,82` asks both to wire request guidance into CFG and to preserve unconditional T2V byte identity. The old builder always emits 5.0. Preserve a golden for the old signature/default CFG 5.0 with a fixed seed; separately assert that intentional non-default guidance changes only the sampler CFG. State whether that guidance fix applies to both T2V and I2V. This is a readily resolvable test-scope ambiguity, not a reason to abandon the upgrade. WAN fps remains hardcoded to 24 today; either document that mapping for this fixed-24-fps stage or test an intentional change rather than implying arbitrary fps is already honored.

### N3 — Keep the fixed clips; choose and verify effective timeout configuration before HG-2

Plan `:94` offers smaller first-run engine params or environment timeout increases. The first option conflicts with the frozen clip set and is not exposed by the copied CLI; the second is already an allowed path and does not require engine changes. Use small params for the separate wrapper smokes, and explicitly select the timeout/configuration gate for the unchanged HG-2 clip. Include the owner model-tag updates in that gate.

Do not present “~25 minutes” as measured for this exact job. The captured default WAN estimator produces 1137 seconds, but its persisted calibration is absent. Naively scaling the entire measured 61-second small run gives about 1780 seconds; treating the tracker-reported 45-second save/decode tail as fixed gives about 512 seconds. Those incompatible extrapolations demonstrate uncertainty, not a proven failure at 600 seconds. LTX's 290.305-second pilot also does not prove a 1–2-minute smoke. Verify effective systemd environment values and full-engine wait/recovery budgets before the operator executes; increasing the wrapper deadline alone is not evidence about an engine runner whose implementation is absent here. These are deployment gates, not justification to change D4 or demand a performance project.

### N4 — Tighten graph/smoke assertions without changing the proven recipe

Plan `:43–44,64–74,84`: make the pilot golden compare the graph's `prompt` node map, not its outer `client_id` envelope. Parameterize audio node 9's frame count/rate alongside nodes 8/5/19; choose one random seed when null and reuse it in both noise nodes. Assert copied-filename wiring at node 31 and per-job output prefixes. Define frame-snap tie/minimum behavior explicitly.

Correct “crop 1280×720” in the mapping-test row to the specified crop-or-pad operation. Add a tiny offline ffmpeg/ffprobe fixture test for exact output dimensions, retained audio, valid MP4, and failed-tail handling; arithmetic alone does not test the served file. Distinguish a 544×960 **base** smoke from the service's final requested dimensions: sending final 544×960 through the documented mapping instead produces a 256×480 base and 512×960 before padding. The existing “base” wording permits the correct smoke, so this is clarification rather than an additional blocker.

### N5 — Deployment and evidence boundaries remain explicit

Keep the no-ComfyUI-restart and owner-confirmed WAN restart rules. Resolve stale scope examples (`q3`, an illustrative WAN tag, media module naming, smoke order) in favor of the implementation plan's concrete values. WAN's schema default `5b` must also be reconciled with served-tag validation or explicitly rejected for omitted variants. Neither new auth/TLS nor a durable database is required for this operator-controlled stage. Binding 0.0.0.0 is not itself proof of tailnet-only reachability; verify the existing host/network access policy when installing, without silently broadening exposure.

In-memory restart loss remains an accepted zero-cost limitation, distinct from B3's demonstrated live state reversal. The exact `reservation_fallback` recovery behavior and upstream 571-test claim remain unverified attestations because their implementations/results were not supplied. Do not copy those inherited numbers into a new “verified” test report. Record the actual peer venv pytest version, collection, pass count, and installation consent at build time; no blanket dependency upgrades or shared-state tests are needed.

## Missed opportunities

A single fake-ComfyUI ASGI contract suite shared across both wrappers would directly cover B1 and prevent drift in no-redirect routing, job IDs, string error bodies, schema/stills refusal, terminal status handling, and output readiness. Include `seed: null` and the engine's exact fixed request as positive fixtures. This is more valuable here than another orchestration abstraction. Keep optional cancel behavior from exposing a lasting `cancelled` status to the frozen adapter, which recognizes it only as poll_failure.

For the next bilateral exchange, respond to B1–B3 individually with amended plan sections and the intended regression assertions. The I2V node-schema read is already a legitimate build prerequisite; supply that evidence at its gate rather than inventing node inputs now. There is no basis in this first bridge vote to assert final-round disagreement or request a tie-breaker.

## Direct answer

The plan is strategically correct but not safe to execute unchanged. Keep the shared Q3/ComfyUI architecture and frozen engine, amend B1–B3, then obtain closure on the amended snapshot before Step 1. The review reproduced the source pin, request/status behavior, graph links and mapping arithmetic, and a real timeout-lifecycle defect in the captured WAN method; it did not independently validate the peer runtime, upstream CI tally, download-helper internals, or full engine recovery. Only this verdict artifact was authorized for repository writes; no implementation, source amendments, services, installs, commits, or pushes were performed.

<!-- HERMES-CONSENSUS-BRIDGE
run_id: 20261114T132812.731698Z-38e3a96a0b
status: COMPLETE
decision: REVISE
expected_head: 4b791dbfb940792178b8287fd5501bbf732fe9ae
expected_fingerprint: a36a74461b6ec76b7cd258f83a08ab85e379b72a2c190e1d0a90246c8b25fd4c
input_sha256: a0e7547d8cd9bc74cf42b84b90aa87af02d7e485431fb849f7e611186f70ae29
named_sources_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
-->
