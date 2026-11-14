# CONSENSUS ROUND 2 (CLOSURE) — LTX wrapper + WAN stills/I2V upgrade plan v1.1

**Date:** 2026-11-14 · **Requested by:** Jose ("Round-2 closure, then build")
**Review type:** Round-two closure audit — NOT a fresh generic review. Walk every prior finding one by one, preserve the original numbering, mark CLOSED / PARTIAL / NOT ADDRESSED with evidence, then run a new-blocker pass over the revision.
**Project:** Wan2.2 fork (peer build for the Locksmith APP ads HG-2 stage)
**Local repo root:** `/home/jose-a-pichardo/Wan2.2` — branch main, HEAD 4b791db. The build target is the peer worktree described in the plan; the peer checkout holds the wrapper code. No pushes; reconciliation is Jose's.

## 1. Source artifact under review

`docs/2026-11-14-ltx-wrapper-implementation-plan.md` — **v1.1**, amended after round 1. Its Provenance section lists every applied amendment (C1–C8 plus the technical non-blockers).

## 2. Prior-round record (read all three)

- `docs/reviews/2026-11-14-ltx-wrapper-plan-round1-CONSENSUS.md` — the reconciled report: consolidated blockers C1–C8 with source mapping, technical non-blockers applied, Jose gates J1–J4
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round1-GPT-VERDICT.md` — GPT seat: blockers B1–B3, non-blockers N1–N5
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round1-OPUS-VERDICT.md` — Opus seat: blockers B1–B5, non-blockers N1–N12

## 3. Named evidence (unchanged from round 1; all beside this input or project-relative)

- `docs/2026-11-14-ltx-wrapper-scope.md` — decided scope D1–D4 (not review targets)
- `peer-evidence.md` — captured WAN wrapper source, proven LTX Q3 graph JSON, verified peer facts (2026-11-14)
- `engine-local-wan.mjs`, `engine-local-ltx.mjs`, `engine-cli.mjs`, `engine-clips.json`, `engine-local-services.json` — verbatim frozen engine copies (Locksmith APP at commit 4d4e4fa)
- The peer is reachable read-only via `ssh -o BatchMode=yes jarvis@100.105.156.94` for live spot-checks (round 1's Opus seat verified node code, configs, calibration, stills, GPUs this way). Never write to the peer, never stop or restart services.

## 4. Required work

### 4a. Closure audit (mandatory, preserves numbering)

For EACH prior finding — GPT B1, B2, B3 and N1–N5; Opus B1–B5 and N1–N12; and the consolidated C1–C8 — mark CLOSED / PARTIAL / NOT ADDRESSED with evidence cited from the amended plan (section and quoted text) and, where relevant, live code. Use the closure table:

```
| Prior finding | Status | Evidence | Residual risk |
```

Judge substance, not keywords: e.g. C1 is closed only if admission genuinely precedes the 202 in the plan's design AND the HTTP tests prove refusal with zero ComfyUI submissions; C5 only if the rewritten chain matches the 5B extra-latents path; C6 only if the round-up math reproduces both the 1280×720 clip and the 1088×1920 golden with no padding anywhere.

### 4b. New-blocker pass (mandatory)

Fresh consistency pass over v1.1 itself: recompute the mapping arithmetic (both routes); check step order and dependencies (Step 0 worktree/venv/goldens before the steps that consume them); check that every promised behavior has a test that actually verifies it; check newly introduced claims against live code where possible — the core ImageScale node and its inputs, WanVideoEmptyEmbeds extra_latents input, WanVideoEncode inputs, the ComfyUI queue-delete and interrupt API shapes, the health-interlock behavior against the engine's health gate, worktree PYTHONPATH imports of the shared media module from both packages, the ffmpeg-tail/atomic-rename ordering, the systemd drop-in mechanism. Internal contradictions between sections are blockers even if all prior findings close.

### 4c. Verdict discipline

All prior findings CLOSED but a new executable blocker exists → still REVISE BEFORE EXECUTION. Closure is necessary, not sufficient. Do not force another fix loop for harmless prose drift when the executable design, tests and acceptance are aligned (late-round convergence rule).

## 5. Requested verdict schema

```
# <SEAT> VERDICT — LTX wrapper + WAN upgrade plan (round 2 closure)
Reviewer: <identity/model>
Date: 2026-11-14
Sources read: <list>

## Verdict
APPROVE | CONDITIONAL APPROVAL | REVISE BEFORE EXECUTION | BLOCKED

## Prior finding closure audit
<the closure table covering GPT B1–B3/N1–N5, Opus B1–B5/N1–N12, C1–C8>

## New-blocker pass
<fresh checks performed, with evidence; any new blockers B-new-1... with claim → evidence → required amendment>

## Non-blockers
<new only, if any>

## Direct answer
<one paragraph: is v1.1 executable now?>
```

## 6. Routing instructions

- Write your verdict to the SIBLING file: `2026-11-14-ltx-wrapper-plan-round2-GPT-VERDICT.md` (beside this input).
- Read-only review + your one verdict file. Do NOT modify the plan or any source; do NOT commit or push.
- Jose's operator gates J1–J4 (still subject review, GPU1 hardware check, his config model tags, measured timeout approval) are acknowledged and gate the live steps, not the plan — do not re-litigate them as plan blockers.
- If you cannot verify a claim either way, name it as an evidence gap rather than guessing.
Bridge expected branch: main
Bridge expected HEAD: 4b791dbfb940792178b8287fd5501bbf732fe9ae
Bridge expected fingerprint: e9be8e1541284d229acf200ae47b39faf65df8174a5de6b2b52712e6450b324d
Bridge named sources SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
