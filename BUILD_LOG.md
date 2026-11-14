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

## Cumulative: 96 passed (Steps 1–4). Next: Step 5 (WAN upgrade: size mapping, 5B I2V chain, admission move, lifecycle, variant, guidance, config-routed paths, /cancel).
