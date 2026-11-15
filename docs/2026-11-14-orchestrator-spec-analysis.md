# Analysis: `dual_rtx5060_comfyui_video_orchestrator_spec.md`

**Date:** 2026-11-14 · **Analyzed for:** Jose's D1 decision (LTX wrapper topology) · **Source file:** `~/Downloads/dual_rtx5060_comfyui_video_orchestrator_spec.md` (open in VS Code)
**Companion:** `2026-11-14-ltx-wrapper-scope.md` (the HG-2 build scope)

## Verdict in one paragraph

The spec is a coherent **production north-star** for 30-second ads on the dual-GPU peer, and several of its patterns are right and adoptable now. But its headline performance claims (Mode A "pools 32 GB, ~1.75–1.90×", Mode B "2.00× linear") rest on hardware and software preconditions that **this peer measurably does not meet**, and every model file and node class its payloads reference is absent from the machine. It is not executable as written, and it should not gate the HG-2 wrapper build. Treat it as a gated R&D track; build the thin wrapper on the proven path now.

## Claim vs verified evidence (all probes read-only, 2026-11-14)

| # | Spec claim | Verified peer reality | Verdict |
|---|---|---|---|
| 1 | Mode A: Raylight FSDP + USP (`ulysses_degree=2`) pools 32 GB, ~1.75–1.90× single-clip speedup; `NCCL_P2P_DISABLE=0` | `nvidia-smi topo -p2p r/w` = **CNS both directions** (no P2P; runbook 2026-11-01 measured the same via torch). NCCL must stage through host memory; USP all-to-all crosses PCIe every layer. The only real dual-GPU experiment here (DisTorch2, tiny 256×256×17f) peaked at **21 GiB host swap** and paged the running ComfyUI | **Contradicted by the only measurement.** Speedup/pooling claims unsupported on this rig |
| 2 | `RayInitActor`, `RayLTXVLoader`, `UnifiedParallelSampler`, `MultiGPUCLIPDeviceSelector` nodes | `custom_nodes/` = ComfyUI-GGUF + ComfyUI-WanVideoWrapper only. **No Raylight, no MultiGPU, no LTX2-MultiGPU; no `ray` in the venv** | Not installed; an install+validation project, not a config change |
| 3 | SageAttention mandatory on all runs | **Not installed** (venv: torch 2.11.0+cu128, triton 3.6.0, no sageattention). Blackwell sm_120 needs a compatible build | Separate validation task |
| 4 | Mode B: two independent ComfyUI workers (:8188 cuda:0, :8189 cuda:1), 2× throughput | Directly conflicts with **Jose's 2026-11-01 ruling: one video-generator service at a time** — the isolated labs were stopped for exactly this. Swap behavior under concurrent load is unvalidated | Requires an explicit ruling change + controlled experiment |
| 5 | Wan 2.2 **14B** FP8 high/low-noise UNets via FSDP; `umt5_xxl_fp8_e4m3fn_scaled`, `wan_2.1_vae`, `ltx-2.5-distilled-fp8` | **14B weights pruned 2026-10-18** (disk). Present: Wan 5B Q8 GGUF; LTX Q3/Q4 GGUF; bf16 T5; conv/audio VAEs; Gemma4 NVFP4 encoder. None of the spec's filenames exist on the peer | ~30+ GB re-download + FSDP validation before any 14B claim |
| 6 | LTX-2.5 **721-frame 30 s single pass** with multi-shot timestamps + synced audio | Proven max: **121 frames / 5 s, 290 s**, Q3 on the shared service, 5.2 GiB host swap at peak. 721f ≈ 6× the latent sequence; the spec's own guardrail splits at 361f | Unvalidated; likely OOM/swap on one 16 GB card. Test 361f segments first |
| 7 | Hardware "2× RTX 5060", paths `/opt/ComfyUI`, venv in `/opt` | Peer is **2× RTX 5060 Ti 16 GB**, ComfyUI at `/home/jarvis/ComfyUI`, venv `/home/jarvis/.venv/wan2.2` | The doc reads as a generic template, not peer-specific; port it before executing anything |

## What the spec gets right — adopt now

- **Distilled CFG=1.0 ⇒ CFG-split parallelism is useless.** Correct, and consistent with the proven Q3 graph (dual CFG 1.0). Any future multi-GPU effort must be sequence/weight parallelism or data parallelism, never CFG split.
- **(N·8)+1 frame rule; half-res base → ×2 latent spatial upscaler; tiled VAE decode.** All already in the proven Q3 graph and in the wrapper scope (§5 mapping).
- **OOM guardrail ladder** (`POST /free` → halve tile size → split frames → drop quant/resolution). Adopt as the wrapper's failure-recovery policy; ComfyUI's `/free` endpoint exists. Maps cleanly onto the engine's definite-4xx vs uncertain semantics.
- **6×5 s shot chaining with last-frame handoff** (`ffmpeg -sseof` frame extraction → next I2V init). The right pattern for 30 s Wan ads — but it belongs in the **ads engine's unit/retake layer** later (the engine already has units, takes, attempts), not in the HG-2 wrapper.
- **Multi-shot timestamp prompts + synced audio** as LTX-2 differentiators worth testing — at the proven 5 s scale first.

## Impact on D1 (the paused decision)

**Recommendation unchanged: the HG-2 LTX wrapper fronts the shared ComfyUI :8188.** The spec offers no executable alternative today — every faster topology it describes needs installs, weights, experiments, and (for Mode B) a ruling change first.

The scoped architecture is **forward-compatible** with the spec's future:
- The wrapper speaks ComfyUI HTTP. If a Raylight unified server ever replaces :8188, only `graph.py` changes.
- If dual workers are ever ruled in, the WAN-style `WorkerPool` shape routes to two ports; the engine contract is untouched.
- The engine's `model_variant` + `local-services.json` seam already accommodates a later 14B or FP8 LTX without engine changes.

**Proposed treatment of the spec:** register it as the "orchestrator track" — a future R&D lane with gates, in order:
1. NCCL/USP micro-benchmark over PCIe with P2P absent (measure, don't assume the 1.75–1.9×).
2. Raylight + ray install and a tiny smoke (17f, 256×256) with swap monitoring.
3. LTX 361-frame segment test on the shared service (the spec's own fallback).
4. 14B re-download decision (disk budget: peer was 84% full after the prune).
5. Jose's ruling on Mode B (one-generator rule change), only after 1–4 produce evidence.

None of these gates HG-2. HG-2's purpose is the engine's first real 0¢ I2V use on the proven path; the orchestrator track is how that path later gets faster.
