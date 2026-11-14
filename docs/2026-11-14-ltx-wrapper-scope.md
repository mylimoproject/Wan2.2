# LTX wrapper build — scope (HG-2 prerequisite)

**Date:** 2026-11-14 · **Status:** DECIDED (D1–D3 ruled by Jose 2026-11-14; D4 default stands; D5 at build kickoff) · **Author:** Qwen Code session (Locksmith roadmap A2/HG-2 prep)
**Builds in:** the peer checkout `/home/jarvis/Wan2.2` on jarvis-rog-x570 (100.105.156.94) · **Serves:** Locksmith APP ads engine `local-test` (plan v1.3.10, S4L)

## Decision log (Jose, 2026-11-14, via ask_user_question)

- **D1 = Shared ComfyUI :8188 + orchestrator spec as a gated future R&D track.** The spec (`~/Downloads/dual_rtx5060_comfyui_video_orchestrator_spec.md`) was analyzed first (`2026-11-14-orchestrator-spec-analysis.md`): its faster topologies need P2P/Raylight/weights this peer lacks; the 5-step validation checklist in the analysis is the future track's gate order. None of it gates HG-2.
- **D2 = Q3** (`ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf`, the proven shared-service path). Q4 stays a later controlled-transition candidate.
- **D3 = LTX wrapper + WAN stills/I2V upgrade** in one build, so both HG-2 routes honor the stills contract and true I2V.
- **D4 = wrapper-owned parameter mapping (§5)** stands as recommended (no engine change); Jose may adjust at review.
- **D5 = repo reconciliation at build kickoff:** build on the peer checkout; any push/reconciliation of the diverged peer↔local commits is Jose's.

## 1. Goal

A REST service on **:8766** that speaks the S4L local contract, so `local-test localtest-<name> --route local-ltx --max-cost-usd 0 --execute` runs an image-to-video clip from a staged still at 0 cents. Scoping surfaced a second gap: **the existing WAN wrapper on :8765 is text-to-video only** — it accepts `image_path` but never uses it, has no `image_sha256` field, and never validates a still. HG-2's clip set is I2V from supplied stills on **both** routes, so the WAN wrapper needs the same stills contract (decision D3).

## 2. The contract (pinned by the engine adapter — not negotiable)

Source of truth: `Locksmith APP/scripts/ads/lib/providers/local-wan.mjs` (shared performer factory; offline tests pin it; 571/571 green).

| Endpoint | Engine expectation |
|---|---|
| `GET /health` | any 2xx = healthy; gates every reservation |
| `POST /generate` | JSON `{prompt, negative_prompt, image_path, image_sha256, width, height, num_frames, fps, num_inference_steps, guidance_scale, seed, model_variant, output_format:"mp4"}` → **202** `{job_id}` with `job_id ~ ^[A-Za-z0-9_-]+$`. **4xx except 429** = definite failure (body `error` or `detail` string, ≤200 chars read). **429/5xx/network/timeout** = uncertain → recoverable, never re-POSTed |
| `GET /status/{id}` | `{status: queued\|processing\|completed\|failed, error?}`; 404 = not_found; other non-2xx = poll_failure |
| `GET /output/{id}` | MP4 bytes; engine bounds the download (250 MiB) and checks the `ftyp` signature; non-2xx preserves job+cost |

Invariants: no Authorization header ever; no redirects (engine sets `redirect:'error'`); the still is referenced by **service-side path + sha256** — image bytes never cross the engine wire; the wrapper resolves the path under its `stillsRoot` and refuses a missing or mismatched still with a definite 4xx.

## 3. Current state (all verified read-only, 2026-11-14)

- **WAN wrapper** `wan_service/` (700 lines): FastAPI → `WorkerPool` (2 GPU queues, round-robin) → `ComfyUIClient` → shared ComfyUI **:8188** (`/prompt`, `/history/{id}`, `/view`) → saves `~/.local/share/wan2.2/outputs/{job_id}.mp4`. Job ids `gen-<uuid4>` (contract-valid). 429 on queue full, 600 s job timeout, self-calibrating ETA, websocket progress. **Jobs are in-memory only** (restart loses them; engine recovery then settles the 0¢ fallback — safe at test stage).
- **Gap W (WAN):** `GenerateRequest` has `image_path` (unused) and **no `image_sha256`**; `build_wan22_workflow` is T2V (`WanVideoEmptyEmbeds`, no LoadImage). Pydantic silently drops the engine's `image_sha256` today.
- **LTX:** nothing listens on :8766; no service unit. LTX has only run as ComfyUI API graphs on the shared :8188. The proven **Q3** graph (`ltx25-tests/q3-default-i2v-pilot-1088x1920-api.json`, 2026-11-01): 290 s, 121 frames, 544×960 → ×2 latent upsample → 1088×1920, **with audio**, distilled 8+3 `ManualSigmas`, `euler_ancestral`, dual CFG 1.0, I2V inplace strength 0.7 (stage 1) / 1.0 (stage 2), tiled VAE decode. Runbook crops 4 px/side to exact 1080×1920.
- **All Q3 model files present:** `unet/ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf` (12 GB), `text_encoders/gemma4-12b-with-proj-ltx-2.5-nvfp4.safetensors`, `vae/ltx-2.5-video-vae-conv-bf16.safetensors`, `vae/ltx-2.5-audio-vae-bf16.safetensors`, `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors`.
- **WAN I2V nodes available** in ComfyUI-WanVideoWrapper: `WanVideoImageToVideoEncode`, `WanVideoImageClipEncode`, `WanVideoImageResizeToClosest`.
- **Stills staged** (Jose-authorized 2026-11-14): `/home/jarvis/{wan,ltx}-stills/locksmith-van-front.png`, sha256 `2b073987f085fa35621272f7af0ab2bf4894281321dfcd8c53d7ae830694fb44` verified on both copies; engine `clips.json` hash set; both-route dry runs green.
- **Services:** `wan2.2.service` + `comfyui.service` enabled/active; venv `/home/jarvis/.venv/wan2.2` (FastAPI/uvicorn/websocket-client present).
- **Ruling (Jose 2026-11-01):** one video-generator service at a time; the isolated LTX labs (:8190/:8191) were stopped; Q4 is validated only in that lab configuration, Q3 is the proven shared-service path.
- **Repo divergence:** peer `/home/jarvis/Wan2.2` @ `3a4b80b` (wrapper commits, unpushed); local fork `main` @ `4b791db` (docs commits). Neither side has the other's work (D5).

## 4. Proposed architecture (D1)

New package **`ltx_service/`** in the peer Wan2.2 repo, mirroring `wan_service` structure and reusing its proven patterns:

- `config.py` — `LTX_*` env: port 8766, `stillsRoot=/home/jarvis/ltx-stills`, output dir `~/.local/share/ltx2.5/outputs`, max queue depth, job timeout (default 900 s), served variant `q3`.
- `schemas.py` — same shapes as WAN **plus `image_sha256`** (required whenever `image_path` is set).
- `main.py` — the four contract endpoints (+ optional `/cancel` like WAN); 429 on queue full; definite 4xx for validation/stills errors.
- `worker.py` — **single** worker → the shared ComfyUI :8188 (no second instance). Before submitting, check ComfyUI `/queue`; if a WAN job is running, answer **429** (engine maps to uncertain → recoverable). Submit graph → poll history → download → save `{job_id}.mp4`.
- `graph.py` — parameterized builder derived from the proven Q3 JSON (LoadImage → LTXVPreprocess → two-stage I2V inplace → ×2 latent upsample → 8+3 sigmas → tiled decode + audio → CreateVideo → SaveVideo). Golden-tested against that JSON.
- `media.py` — **shared stills guard** (also adopted by WAN under D3): resolve `image_path` strictly under `stillsRoot` (refuse traversal/absolute escapes), sha256-compare against `image_sha256`, then copy into `ComfyUI/input/` as `{job_id}-{basename}` for LoadImage.
- `ltx.service` — systemd unit, same venv, `uvicorn ltx_service.main:app --host 0.0.0.0 --port 8766 --workers 1`, `Restart=on-failure`. **Enabled only after the live smoke passes.**

Topology rationale: the generator is ComfyUI (one instance, per the ruling); the wrappers are thin HTTP frontends. ComfyUI serializes jobs internally; the queue interlock prevents WAN/LTX model-swap churn mid-job. The engine runs one route per `local-test` invocation anyway.

## 5. Parameter mapping (D4 — wrapper owns it; engine and clips.json unchanged)

The engine sends the shared WAN-shaped params (1280×720, 97 frames, 50 steps, cfg 5.0). The distilled LTX recipe differs; the wrapper maps and documents:

| Engine field | LTX mapping |
|---|---|
| width × height | stage 1 = half-res snapped to multiples of 32 (1280×720 → 640×352); ×2 upsample → 1280×704; ffmpeg crop/pad tail to the exact requested 1280×720 (runbook crop precedent) |
| num_frames | kept when valid (97 = 8·12+1 ✓); snapped to 8k+1 otherwise |
| fps | 24 (LTXVConditioning + CreateVideo) |
| num_inference_steps | **ignored** in favor of the proven fixed 8+3 distilled sigmas (50 steps is meaningless on a distilled schedule) |
| guidance_scale | fixed 1.0 (distilled dual CFG) |
| seed | RandomNoise, both stages |
| model_variant | must equal the served variant, else definite 4xx |
| audio | kept (proven graph generates it; the contract only checks MP4) |

## 6. WAN wrapper upgrade (D3)

- `schemas.py`: add `image_sha256`; `media.py` stills guard on both services.
- `worker.py`: when `image_path` is present, build the **I2V variant** — LoadImage → `WanVideoImageResizeToClosest` → `WanVideoImageToVideoEncode` (replaces `WanVideoEmptyEmbeds`) → existing sampler/decode/save chain. T2V path preserved when no image.
- `model_variant` validated against the served `5b-gguf`.
- **Jose's config fix:** `local-services.json` `local-wan.model` currently names the pruned `wan2.2-14b-fp8`; set it to the agreed 5B tag (e.g. `wan2.2-ti2v-5b-q8_0`) — with strict variant validation the engine's `model_variant` must match. `local-ltx.model` likewise agreed (e.g. `ltx-2.5-q3`). That file is Jose's by rule.

## 7. Verification plan

1. **Offline pytest** (peer venv, no GPU/ComfyUI): schema validation; stills traversal + hash-mismatch refusal; graph builder golden test vs the proven Q3 JSON; mapping snap/crop math; 429 interlock logic.
2. **Controlled live smoke** (Jose-authorized, one generator at a time, small params): curl health → generate with the staged still → poll → output → ffprobe + sha256. WAN I2V smoke first, then LTX.
3. **Engine HG-2 (Jose runs):** `local-test … --execute` per route; verify job-state/3 file, one 0¢ `provider_reported` ledger line, output MP4; visual review of both clips.
4. **Rollback:** `ltx.service` stays disabled until smoke passes; WAN changes on a branch until its smoke passes; no change to ComfyUI itself.

## 8. Risks

- **VRAM/model-swap churn** WAN↔LTX on one ComfyUI: Q3 pilot peaked GPU0 14.8 GB of 16 GB with 5.2 GiB host swap. Mitigations: sequential runs, queue interlock, Q3 (not Q4) first.
- **In-memory job table:** a wrapper restart loses jobs → engine recovery settles the 0¢ fallback (safe now; durable job state is later hardening, out of scope).
- **Timeouts vs production-shaped params:** 97f×50 steps at 1280×720 ≈ ~25 min on WAN vs its 600 s job timeout. HG-2 should use smaller first-run params (Jose's decision) or raise the timeout env.
- **Repo divergence** (D5): building on the peer without reconciling risks losing the local docs commits or vice versa.
- **Crop tail** needs ffmpeg on the peer (present; used by the runbook).

## 9. Decisions for Jose

- **D1 — Topology:** LTX wrapper fronts the **shared ComfyUI :8188** (recommended; fits the one-generator ruling) vs a second ComfyUI instance (requires changing the ruling; the labs were stopped for exactly this). Jose's orchestrator spec (`~/Downloads/dual_rtx5060_comfyui_video_orchestrator_spec.md`) was analyzed 2026-11-14 — see `2026-11-14-orchestrator-spec-analysis.md`: its faster topologies need installs/weights/experiments this peer doesn't have yet; recommendation unchanged, spec proposed as a gated future R&D track.
- **D2 — LTX quant:** **Q3** (proven on the shared service; recommended for HG-2) vs Q4 (higher quality, validated only in the stopped lab; needs an authorized controlled transition).
- **D3 — Build scope:** **LTX wrapper + WAN stills/I2V upgrade** (recommended — otherwise the WAN clip silently ignores the still and HG-2's I2V intent fails on one route) vs LTX-only now, WAN later.
- **D4 — Parameter mapping:** wrapper-owned mapping per §5, no engine change (recommended) — approve or adjust.
- **D5 — Repo reconciliation:** peer wrapper commits (`fc0f21c`, `3a4b80b`) vs local `main` docs commits — how to sync before building (any push is Jose's).

Also pending from prep: the `local-services.json` model fields (§6) and first-run clip params.

## 10. Out of scope

Engine changes (S4L is frozen and CI-green), paid routes, durable job store, auth/TLS (tailnet posture unchanged from WAN), reviving the Q4 labs, ad-pack finishing. HG-2 remains Jose's run under operator policy A1(b).
