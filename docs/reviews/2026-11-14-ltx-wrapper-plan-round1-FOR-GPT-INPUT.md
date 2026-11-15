# CONSENSUS ROUND 1 — LTX wrapper + WAN stills/I2V upgrade implementation plan

**Date:** 2026-11-14 · **Requested by:** Jose ("implementation plan first with its verification/review pipeline right after (consensus bridge)")
**Review type:** Round A independent review (bilateral loop continues in Round B/C if needed)
**Project:** Wan2.2 fork (peer build) serving the Locksmith APP ads engine's local-test stage (S4L, plan v1.3.10)
**Local repo root:** `/home/jose-a-pichardo/Wan2.2` — branch main, HEAD 4b791db (docs-only). The BUILD happens on the peer checkout on jarvis-rog-x570 (commit 3a4b80b), which holds the wrapper code; the two checkouts are diverged and reconciliation is Jose's — do not propose pushes.

## 1. What is being reviewed

The implementation plan at `docs/2026-11-14-ltx-wrapper-implementation-plan.md`.

It builds (a) a new LTX-2.5 REST wrapper (the ltx_service package, port 8766) on the ROG peer fronting the shared ComfyUI on port 8188 with the proven Q3 graph, and (b) an upgrade of the existing WAN wrapper (port 8765) to honor stills + true I2V. Both must speak the frozen S4L engine contract so Jose can run the HG-2 real clips at 0 cents.

## 2. Named sources (read these; do not trust this summary alone)

Plan + context (project-relative):
- `docs/2026-11-14-ltx-wrapper-implementation-plan.md` — THE SOURCE ARTIFACT
- `docs/2026-11-14-ltx-wrapper-scope.md` — decided scope (D1 shared ComfyUI, D2 Q3, D3 LTX+WAN; decision log at top)
- `docs/2026-11-14-orchestrator-spec-analysis.md` — why the dual-GPU orchestrator spec is a gated future track, not this build

Engine contract — VERBATIM COPIES of the frozen S4L files from the Locksmith APP repository at commit 4d4e4fa (CI-green, 571/571 offline tests; no engine changes allowed). Copies live beside this input:
- `engine-local-wan.mjs` — the shared performer factory: exact request fields, 202/4xx/429 semantics, status strings, job-id regex, bounded MP4 download, health gate
- `engine-local-ltx.mjs` — LTX adapter (same factory, providerTag local-ltx)
- `engine-cli.mjs` — the CLI; localTestHandler near line 686: dry run, health gate, all-zero sha refusal, owner purity, 0-cent ceiling, seed-change retries
- `engine-local-services.json` — origins + stillsRoots + model fields (Jose's file; model fields still name the pruned 14B — the plan pins new tags)
- `engine-clips.json` — the fixed clip set (1280×720, 97 frames, 50 steps, cfg 5.0; real still sha256 now set)

Peer-only evidence (captured read-only 2026-11-14 from jarvis-rog-x570; the peer is not reachable from your sandbox — this file IS the live peer state):
- `peer-evidence.md` — FULL source of the WAN wrapper package (config, schemas, main, worker modules), the FULL proven LTX Q3 I2V API graph JSON, and the verified-facts list (P2P absent, nodes/packages present/absent, model files, systemd units, health probes, staged stills + hashes, runbook pilot measurements, one-generator ruling)

## 3. Decisions already ruled by Jose (not review targets)

- D1: the LTX wrapper fronts the SHARED ComfyUI on port 8188 (one-generator ruling of 2026-11-01 stands; no second instance).
- D2: Q3 quant (the ltx-2.5-22b-distilled-UD-Q3_K_XL GGUF), the proven shared-service path.
- D3: one build covering the LTX wrapper AND the WAN stills/I2V upgrade.
- D4: wrapper-owned parameter mapping; engine and clip set unchanged.
- Operator policy: Jose runs all live execute takes and authorizes live smokes; agents build + offline-test. Restarting the WAN generator service needs his explicit confirmation. No pushes.

## 4. Requested verdict schema (write EXACTLY this structure)

```
# GPT VERDICT — LTX wrapper + WAN upgrade plan (round 1)
Reviewer: <identity/model>
Date: 2026-11-14
Sources read: <list>

## Verdict
APPROVE | CONDITIONAL APPROVAL | REVISE BEFORE EXECUTION | BLOCKED

## Live-code spot-check lens (mandatory)
<what you freshly read in the named sources; contract fields verified against the adapter code; graph claims verified against the Q3 JSON; WAN claims verified against the worker source; mapping math recomputed; any mismatch with the plan's prose>

## Blockers (B1, B2, ...)
<each: claim in plan → evidence (file + line/section) → why it blocks execution → required amendment>

## Non-blockers (N1, N2, ...)
<same shape, severity justified>

## Missed opportunities
<optional>

## Direct answer
<one paragraph: is this plan safe and executable as written?>
```

Blockers = contradictions, missing required behavior, security/safety issues, unverifiable acceptance criteria, stale paths that break execution, or plan/code mismatches likely to produce a bad implementation. Improvements are NOT blockers.

## 5. Review lenses (cover all)

1. **Contract fidelity lens** — every endpoint/field/status/error mapping in the plan vs the adapter code (202 + job-id regex; 4xx-except-429 definite; 429/5xx uncertain; status strings queued/processing/completed/failed; 404 not_found; MP4 ftyp + 250 MiB bound; no redirects; no Authorization; model_variant strictness; seed null handling).
2. **Stills/safety lens** — containment (parent traversal, absolute escapes, symlinks), sha256 comparison, TOCTOU between validate and copy, filename collisions in the ComfyUI input dir, LoadImage path semantics, key-free/no-egress guarantees, restart/rollback gates, one-generator compliance, the 429 interlock's race behavior.
3. **Graph/mapping lens** — builder fidelity to the proven Q3 JSON (node ids, links, sigmas, I2V strengths 0.7 and 1.0, audio path, conditioning frame rate, empty-latent length, tiled decode params); the divide-by-32 snap math (1280×720 → 640×352 → 1280×704 → pad to 720); 8k+1 frames; the WAN I2V node-schema hypothesis flag (plan Step 5); the guidance-scale hardcode gap; the WAN T2V byte-identity claim.
4. **Planning/test lens** — step order and dependencies; do the listed tests actually verify the promised behavior (golden graph, mapping, interlock, stills refusal, T2V identity); acceptance criteria verifiable; smoke params sane vs the runbook measurements (Q3 121 frames = 290 s with 5.2 GiB host swap; WAN 17 frames × 10 steps = 61 s); timeout budgets (WAN 600 s vs ~25-min production params; LTX 900 s); in-memory job table consequences for engine recovery; the pytest-in-venv install visibility.

## 6. Routing instructions

- Write your verdict to the SIBLING file: `2026-11-14-ltx-wrapper-plan-round1-GPT-VERDICT.md` (beside this input, in the reviews directory).
- Do NOT modify the plan, scope, analysis, engine copies, or any source. Do NOT commit or push anything. Read-only review + your one verdict file.
- The peer is reachable via `ssh -o BatchMode=yes jarvis@100.105.156.94` for READ-ONLY spot-checks if your environment allows it; the captured evidence file is the authoritative fallback. Never stop/restart services, never write to the peer.
- If you cannot verify a claim either way, say so explicitly as an evidence gap rather than guessing.
Bridge expected branch: main
Bridge expected HEAD: 4b791dbfb940792178b8287fd5501bbf732fe9ae
Bridge expected fingerprint: a36a74461b6ec76b7cd258f83a08ab85e379b72a2c190e1d0a90246c8b25fd4c
Bridge named sources SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
