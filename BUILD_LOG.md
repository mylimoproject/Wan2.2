# HG-2 wrapper build log (plan v1.3, worktree hg2-wrappers)

## Step 0 — setup (2026-11-14)
- Worktree `/home/jarvis/Wan2.2-hg2` @ 3a4b80b, branch hg2-wrappers; live tree untouched.
- Test venv `/home/jarvis/.venv/wan2.2-hg2-tests`: /usr/bin/python3.12 (3.12.3), pytest 9.2.0 ONLY here; read-only .pth to the shared runtime site-packages.
- Preflight recorded (tests/fixtures/step0-preflight.txt): fastapi 0.143.3, pydantic 2.14.1, httpx 0.28.1, starlette 1.8.0 — all from the shared venv; wan_service from the worktree. Empty collection rc=5 accepted.
- Goldens: wan_t2v_golden.json (9 nodes, seed 42, 704×1280, unmodified code; sha daf4a3c2…); ltx_q3_pilot.json pinned (sha 8df04851a885d136…).

## Step 1 — local_media.py (26 tests)
- Stills snapshot guard: dir-fd walk with O_NOFOLLOW per component, read-once/hash/exclusive-write, sanitized components, unique per-job destination, cleanup helper.
- Shared ffmpeg tail: center-crop to exact size, never pad, -c:a copy, atomic rename, exact-dims rename-only path.
- Bugs caught by the suite and fixed: (1) O_RDONLY open of a FIFO blocks until a writer exists → added O_NONBLOCK so fstat can reject non-regular files; (2) ffmpeg could not infer the muxer from the .tmp temp name → explicit -f mp4.

## Step 2 — ltx_service config/schemas (20 tests)
- I2V-required image_path + image_sha256 (hex64, normalized), single served-variant setting (ltx-2.5-q3) driving default+validation, queue depth 1, 900 s default timeout, env-driven paths.

## Step 3 — ltx_service graph builder (27 tests incl. golden)
- **GOLDEN CATCH:** the first implementation was built from a misremembered version of the captured graph (28 nodes, DualCFGGuider/SamplerCustomAdvanced wiring, long pilot prompt). The authoritative pinned fixture is a 31-node graph using LTXVEmptyLatentAudio, LTXVConcatAVLatent, LTXVSeparateAVLatent, LTXVDualCFGGuider (shared guider for both stages), seed 42, short pilot prompt, SaveVideo prefix ltx25-hermes-hires/… (matching the actual proven pilot output). The golden test failed, the diff was taken against the fixture, and the builder was rebuilt node-for-node from it. The round-1 peer-evidence capture already contained the true graph; both consensus seats verified against it — the drift was implementation-side only.
- Note: plan-prose node numbers are indicative (e.g. "node 31 filename" — node 31 is LoadImage; the SaveVideo prefix is node 20). Design semantics are unchanged: frames drives the video AND audio latent nodes; fps drives conditioning, audio latent and CreateVideo; prompts, image, seed, dims and prefix are the parameterized fields. No design change → no re-consensus required.
- Mapping verified: 1280×720 → 640×384 → 1280×768 → crop 24/side; 1080×1920 → 544×960 → 1088×1920 (golden, crop 4/side); never undershoots; frame snap 8k+1 min 17, ties up.

## Step 4 — ltx_service worker + main (23 tests: 12 admission HTTP, 10 lifecycle, 1 interlock)
- Admission before 202 under an asyncio lock: schema → variant → busy/unavailable → stills LAST; zero ComfyUI submissions on refusal; slot released on refusal; /health interlock (non-2xx when ComfyUI down or queue busy); 400 handler replaces FastAPI 422; redirect_slashes=False; /cancel reports status failed + error cancelled (never "cancelled").
- Worker: single slot, executor generation loop, monotonic terminal states, prompt-TARGETED interrupt only (decide_cancel_action pure policy), pending-delete then re-read, draining ownership until own prompt absent/terminal (double-observation gone check) AND gen thread quiesced; staged input cleaned only then; late success/error never publishes.
- Harness bugs caught and fixed: (1) TestClient without a context manager spins a fresh event loop per request → the shared admission lock deadlocked under concurrent admission; fixed with one persistent portal (with TestClient(...)); (2) pgrep -f cleanup matched the SSH shell's own command line (which contained the pytest invocation text) and killed itself — cleanup must run in a separate session from the run; (3) a lifecycle test raced its own late-complete against the drain's first queue read — reordered to observe the targeted interrupt first.
- Post-Step-4 R3-1 preflight: wan_service.main + ltx_service.main + local_media all import OK.

## Step 5 — WAN upgrade (2026-11-14)
- INPUT_TYPES confirmed on the peer BEFORE edits (read-only object_info): WanVideoEncode requires vae, image, enable_vae_tiling plus tile_x/tile_y 272 and tile_stride_x 144 / tile_stride_y 128; WanVideoEmptyEmbeds has optional extra_latents (LATENT); ImageScale offers lanczos and center. Plan §4b chain is valid as written.
- config: SERVED_VARIANT 5b-gguf (one setting drives schema default, validation, /health), STILLS_ROOT wan-stills, COMFYUI_INPUT_DIR, CALIBRATION_PATH env-routed (NB-1), MAX_QUEUE_DEPTH 1, WAN_PROGRESS_WS flag.
- schemas: image_sha256 (hex64) required with image_path; T2V stays legal without a still; LTX-style range validators; RequestValidationError handler returns 400 {error, detail}.
- main: admission BEFORE the 202 under an asyncio lock (schema → variant → busy 429/503 → stills last, T2V skips staging); /health interlock; redirect_slashes=False; /cancel reports failed + cancelled, monotonic.
- worker: single-slot WanWorker mirrors the LtxWorker lifecycle (terminal states terminal, prompt-TARGETED interrupt/delete only, draining ownership, late results never publish); map_size rounds each dim UP to /32 (1280×720 → 1280×736) and the shared ffmpeg tail crops to exact; I2V chain nodes 10 LoadImage → 11 ImageScale (lanczos/center, generated size) → 12 WanVideoEncode (all seven required inputs) → node 5 extra_latents; guidance_scale wired to sampler cfg for T2V and I2V; all output writes through config.OUTPUT_DIR; progress websocket + self-calibrating ETA kept (ws hermetic-off in tests). WorkerPool removed: one ComfyUI, one slot.
- T2V golden byte-identical: sorted-keys JSON equals the pinned fixture (sha daf4a3c2…) for the proven 704×1280 default shape with default cfg.
- Shared suites now run BOTH routes (fake_comfy make_env/make_rig/body; per-route exception classes — WAN never imports ltx_service). New: test_wan_size_mapping (10), test_wan_i2v_graph (9); HTTP traversal refusals added for both routes.
- Suite: 150 collected, 147 passed, 3 skipped (route-exclusive: LTX skips WAN's two T2V tests; WAN skips the I2V-only missing-still refusal). Both-wrapper R3-1 preflight green (imports + shared-venv origins, interpreter 3.12.3).
- Live tree and services untouched; wan-stills/locksmith-van-front.png already staged. Smoke scripts belong to Steps 7/8 and were not written here.

## Step 7 — install files + ltx.service installed (2026-11-14, Jose-authorized via SSH)
- **PORT RULING (Jose, 2026-11-14):** the plan's 8766 is held by command-post's API (127.0.0.1:8766, up since boot). LTX moves to **8767** — a config-only deviation (unit LTX_PORT + Jose's local-services.json baseUrl); engine contract semantics unchanged; command-post untouched.
- Files: `systemd/ltx.service` (User=jarvis, worktree WorkingDirectory/PYTHONPATH, shared-runtime uvicorn, 0.0.0.0:8767, Restart=on-failure; [Install] present but NOT enabled), `scripts/install-ltx-service.sh` (sudo copy + daemon-reload + start only; refuses a busy 8767; prints network policy), `scripts/ltx-smoke.sh` (Jose runs: 33 frames, final 1280×720, seed 42, fixed 8+3; /health gate → 202 → poll → ffprobe h264+audio exact dims → sha256 receipt under ~/ltx-smoke-receipts/<ts>/; DRY_RUN=1 offline mode).
- Offline checks: bash -n both scripts; systemd-analyze verify clean; DRY_RUN request shape + still sha 2b073987… verified against the J1-approved staged still.
- INSTALL receipt: ltx.service **active**, /health {"status":"ok","model":"ltx-2.5-q3","queue_depth":1}; listener 0.0.0.0:8767; ufw default deny incoming with ALLOW only on tailscale0 (+ LAN 22/tcp) → tailnet-only reachability verified, including a health GET from jarvis-sister over the tailnet (the engine's exact origin). wan2.2.service + comfyui.service untouched and active; WAN :8765 still answering. ltx.service **NOT enabled** (enable only after the smoke passes).
- Pre-existing host noise: /etc/sudoers.d/openclaw-oom emits a wildcard sudoers warning on every sudo call (unrelated to this build).
- **LIVE SMOKE PASS (2026-11-14 23:07, Jose authorized "run the smoke"):** job gen-f3acf8e5-479a-495a-92dd-5c497c391e18 completed; clip sha256 d8a53703f6fd672be6e2812c657a4f176613527f484dd78692d39a4e8c0135d3; ffprobe h264 1280×720 + aac; duration 1.375 s (33/24); post-job /health ok, 0 staged copies left in ComfyUI/input, all three services active. Receipt: /home/jarvis/ltx-smoke-receipts/20261114T230718/. Supplementary frame-16 check (transcription-based): subject, clothing, vehicle and setting match the J1 still; final visual review is Jose's.
- ENABLED (Jose, 2026-11-14): `systemctl enable ltx.service` after the passed smoke — is-enabled=enabled, is-active=active, /health ok. J3 closed the same night (tags byte-exact vs /health). Remaining: Step 8 (J4 measured timeout + confirmed WAN restart + WAN I2V smoke), then Step 9 takes.

## Cumulative: 147 passed + 3 route-exclusive skips (Steps 1–5). Step 6's checks (both-wrapper preflight + full suite + recorded counts) ran green in the same session. Step 7 install done; next is Jose's J3 tags + LTX live smoke, then Step 8.
