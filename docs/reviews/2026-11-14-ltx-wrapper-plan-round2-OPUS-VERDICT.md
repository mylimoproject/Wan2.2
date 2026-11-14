# OPUS VERDICT — LTX wrapper + WAN upgrade plan (round 2 closure)
Reviewer: Claude Opus 5.5 (`claude-opus-5-5`), Opus seat. I reviewed independently of the GPT seat, read-only: I wrote no files, and on the peer I only read and ran probes.
Date: 2026-11-14
Sources read:
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round2-FOR-GPT-INPUT.md`
- `docs/2026-11-14-ltx-wrapper-implementation-plan.md` (v1.1, in full)
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round1-CONSENSUS.md`, `…-GPT-VERDICT.md`, `…-OPUS-VERDICT.md` (all in full)
- `peer-evidence.md` (in full); `engine-local-wan.mjs` (in full); `engine-cli.mjs` `localTestHandler` (lines 680–801); `engine-clips.json`; `engine-local-services.json`
- **Live peer reads over SSH, read-only:**
  - ComfyUI `c06bf5f56`: `nodes.py` (`ImageScale`), `server.py` (`/interrupt`, `POST /queue`, `GET /queue`), `execution.py` queue accessors.
  - WanVideoWrapper `088128b`: `nodes.py` (`WanVideoEncode`, `WanVideoEmptyEmbeds`) and `nodes_sampler.py` (extra_latents and 5B clean-latent path), plus the wiring of `wanvideo_2_2_5B_I2V_example_WIP.json`.
  - Service and repo state: `systemctl cat` / `systemctl show wan2.2.service`; peer git and worktree state; the shared venv's `pyvenv.cfg` and module visibility; system Python versions and site-packages.
  - Hard-coded paths in `wan_service/*.py`; ffmpeg encoders; an ffprobe of the proven LTX pilot output; live `GET :8188/queue`.

## Verdict
REVISE BEFORE EXECUTION

All 33 prior findings close except Opus-N7, which is PARTIAL. One new blocker that can actually fire was found and confirmed on the peer: the Step 0 test venv cannot import the wrappers' runtime stack. The fix is a mechanical amendment to §0.7 and Step 0, with no design change. A third full review round is not needed; a check that the amended text has landed is enough to close it (§4c rule).

## Prior finding closure audit

| Prior finding | Status | Evidence | Residual risk |
|---|---|---|---|
| **GPT-B1** admission before 202 | CLOSED | §2: "Admission runs synchronously in `main.py` BEFORE the 202 and before any queueing (both services; WAN's checks move out of the worker)". The tests prove "exact 400/429/503 bodies, **zero ComfyUI prompt submissions on any refusal**, valid 202 ids, subsequent status/output/404". §3 has the shared `test_admission_http.py` for both wrappers. | The tests can't run in the specified venv (B-new-1). Lock placement and `/prompt`-400 placement are unclear (NB-4). |
| **GPT-B2** stills snapshot integrity | CLOSED | §2.1–2.3: `is_relative_to(root.resolve())`, regular file only, "refuse symlink escapes at every component", "Read the file once, hash those exact bytes … write those same bytes … `open(dst,'xb')` … never reopen the source". The O_EXCL open fails with EEXIST on a pre-existing symlink. §2.5 has the race, byte-hash and same-basename tests. | A copy staged before a 429/503 refusal leaks (NB-5). |
| **GPT-B3** timeout state reversal | CLOSED | §5: "A timed-out or cancelled job is `failed` **forever** … tracked as *draining* … next job hands off only when the slot is genuinely free". Regressions: "timeout→late success, timeout→late error, terminal-state monotonicity, resource ownership, next-job handoff, orphan cleanup". This applies to both wrappers. | WAN `/cancel` can bring a queued job back to life (NB-6). |
| **GPT-N1** advisory interlock | CLOSED | §5: "The interlock is **advisory** … No distributed scheduler". The `test_interlock.py` "simultaneous admissions" case is included. | None. |
| **GPT-N2** T2V identity / guidance / fps | CLOSED | §3 WAN worker: "`guidance_scale` wired to sampler cfg for T2V and I2V … fps stays hardcoded 24 — documented"; the golden is "for the proven 704×1280 default shape with default cfg". | Low. |
| **GPT-N3** timeout gate, no smaller params | CLOSED | Step 8 is a measured gate; "smaller params" is removed (Provenance C7). §7: "extrapolations are never reported as measured". Step 8: "Verify effective systemd env". | The measurement path is not named (NB-8). |
| **GPT-N4** graph and smoke assertions | CLOSED | §3 golden "compares the **prompt object**"; §4: node 9 `frames_number`, fps on nodes 5/9/19, seed reused in both noise nodes, node 31 parameterized, per-job prefix, explicit snap tie/minimum. `test_ffmpeg_tail.py` exists. Step 7: "final-request 1280×720 (mapping yields 640×384 base)". | None. |
| **GPT-N5** deployment and evidence boundaries | CLOSED | §0.5 has the network-policy check. §1 has one variant setting. Steps 0 and 6 say "record actual pytest version, collection and pass counts — no inherited numbers". §7 has the in-memory limitation. | Recorded counts depend on B-new-1. |
| **Opus-B1** WAN 1280×720 invalid on 5B | CLOSED | §4b: "nearest /32 **≥** … 1280×720 → **1280×736**, generate, then ffmpeg center-crop 8 px per side … **Never pad**". Step 8 smokes at a 1280×720 request. Recomputed: 736//8=92, the 5B sampler halves it to 46, 46/2=23 patches (integer). | Where the WAN crop tail lives, its ordering and its tests are unspecified (NB-2). |
| **Opus-B2** wrong I2V chain | CLOSED | §4b: "`LoadImage` → **core `ImageScale`** (lanczos, … `crop:"center"`) → **`WanVideoEncode`** → **`WanVideoEmptyEmbeds`(…, extra_latents)** → node 6". Verified live in "New-blocker pass". | `WanVideoEncode` has five required tile inputs the plan does not list (NB-7). |
| **Opus-B3** LTX rounds down / letterbox | CLOSED | §4: "rounded **UP** to /32: 1280×720 → 640×384; ×2 → 1280×768; … crop 24 rows per side … **Never pad.**" The math is reproduced below. | None. |
| **Opus-B4** timeout plus orphaned prompts | CLOSED | (a) Step 8 measured drop-in, approved by Jose (J4). (b) §5: "if **this wrapper's own prompt** is running → `POST /interrupt`; if pending → `POST /queue {"delete":[id]}`. **Never blind-interrupt**". | There is a race between the `/queue` check and the interrupt; ComfyUI's targeted interrupt removes it (NB-3). |
| **Opus-B5** live-tree build | CLOSED | §0.4: worktree `/home/jarvis/Wan2.2-hg2`; "`ltx.service` points at the worktree. WAN moves only at Step 8 by fast-forward". Rollbacks are independent. Peer confirmed: main at `3a4b80b`, clean, one worktree, no `hg2-wrappers` branch yet; the unit runs from `/home/jarvis/Wan2.2` with `Restart=on-failure`. | None. |
| **Opus-N1** interlock, lock, GPU ids, depth | CLOSED | §3: "**asyncio.Lock around the busy-check + submit**", "**queue depth 1**", WAN "busy-check added", §5 `WAN_GPU_IDS=0`, the advisory label, and §1 `/health` as the interlock. | The lock sits in `worker.py` but the busy check is in `main.py` (NB-4). |
| **Opus-N2** validation placement | CLOSED | Same evidence as GPT-B1/C1. | — |
| **Opus-N3** three variant settings | CLOSED | §1/§4b: "One setting drives schema default, validation and /health … A bare request without `model_variant` gets the served default (regression-tested)". | None. |
| **Opus-N4** 422 and `/prompt` 400 mapping | CLOSED | §1: "`RequestValidationError` handler returning 400 `{error, detail}`". §2: "`/prompt` answering 400 with `node_errors` … definite 4xx, not 503". | Where `/prompt` is called is ambiguous (NB-4). |
| **Opus-N5** LTX parameter coverage | CLOSED | §4: num_frames drives node 8 length AND node 9 frames_number; fps drives 5/9/19; node 31 parameterized; the golden compares the prompt object and is sha-pinned. | None. |
| **Opus-N6** stills guard details | CLOSED | Same evidence as C2; §2.4 "LTX **requires** `image_path`". | NB-5. |
| **Opus-N7** test venv and conftest | **PARTIAL** | §0.7 / Step 0: "creates `/home/jarvis/.venv/wan2.2-hg2-tests` with `--system-site-packages` and pytest. `conftest.py` sets `WAN_OUTPUT_DIR`/`LTX_OUTPUT_DIR`". **The mechanism does not work.** `--system-site-packages` exposes the *base* interpreter's site-packages, not the shared venv's. Confirmed live: the shared venv is `home=/usr/bin`, 3.12.3, `include-system-site-packages=false`. `/usr/bin/python3.12` and `/usr/bin/python3` (now **3.14.4**) see none of fastapi, httpx, pydantic, uvicorn or starlette. The conftest isolation also misses paths under `Path.home()`. | **B-new-1**; NB-1. |
| **Opus-N8** golden from unmodified code | CLOSED | Step 0: "capture the T2V golden from unmodified code (fixed seed)", taken before any edit. | Needs a pydantic-capable interpreter (B-new-1). |
| **Opus-N9** executor, atomic rename, `-c:a copy` | CLOSED (LTX) | §3 LTX worker: "ffmpeg exact-size tail → **atomic rename into place; `completed` only after the rename** … blocking calls + ffmpeg in an executor"; §4 `-c:a copy`. The pilot output ffprobes as mp4 / h264 yuv420p / **aac**, so stream copy is valid. libx264 is present (ffmpeg 8.0.1). | The WAN tail has no equivalent ordering (NB-2). |
| **Opus-N10** unit template | CLOSED | §3: "`User=jarvis` …, WorkingDirectory + PYTHONPATH = the **worktree**, venv uvicorn … `--workers 1`, Restart=on-failure". This mirrors the live `wan2.2.service`. | None. |
| **Opus-N11** still subject and aspect | CLOSED (routed) | Jose gate J1, §9. | Jose's call. |
| **Opus-N12** GPU1 fault | CLOSED (routed) | Jose gate J2; Step 7 "J2 hardware check first"; `WAN_GPU_IDS=0`. | Jose's call. |
| **C1** admission boundary | CLOSED | See GPT-B1. Admission precedes the 202 in the design, and the HTTP tests assert zero submissions on refusal. | B-new-1 makes those tests unrunnable as specified. |
| **C2** stills snapshot | CLOSED | See GPT-B2. | NB-5. |
| **C3** terminal-state monotonicity | CLOSED | See GPT-B3 and Opus-B4(b). The API shapes are confirmed live: `POST /queue {"delete":[…]}` matches `item[1]`; `GET /queue` items are `(number, prompt_id, …)`. | NB-3, NB-6. |
| **C4** WAN /32 mapping | CLOSED | See Opus-B1. The 704×1280 shape passes through unchanged (704 = 22·32). | NB-2. |
| **C5** 5B I2V chain | CLOSED | Matches the shipped 5B example's wiring and the sampler's extra_latents path (see the new-blocker pass). | NB-7. |
| **C6** LTX round-up | CLOSED | 1280×720 → 1280×768 → crop 24/side; the 1088×1920 golden is reproduced; padding never occurs. | None. |
| **C7** measured timeout gate | CLOSED | Step 8: "derive `WAN_JOB_TIMEOUT_SECONDS` ≥ 2× the measured/extrapolated HG-2 time … **together with** the fast-forward of main and the **Jose-confirmed WAN restart**. Verify effective systemd env." | NB-8. |
| **C8** worktree isolation | CLOSED | See Opus-B5. | None. |

## New-blocker pass

**Mapping arithmetic, both routes (recomputed):**
- **LTX:**
  - 1280×720: half 640×360 → round up to /32 → **640×384** → ×2 = 1280×768 → crop (768−720)/2 = **24/24** → 1280×720.
  - 1088×1920: 544×960, already on the 32-grid, equals pilot node 8; no crop.
  - Runbook case 1080×1920: 540→544 → 1088×1920 → crop 4 px a side.
  - 2·ceil32(⌈w/2⌉) ≥ w for every w, so padding can never occur. Stage-2 pixel cost is +9.09%.
  - Frames: 97 = 8·12+1, 33 = 8·4+1, 17 = 8·2+1.
- **WAN:**
  - 1280×720 → **1280×736**. EmptyEmbeds target (16, 25, 92, 160); the 5B sampler gives (48, 25, **46, 80**); that is 23×40 patches; decode gives 736×1280; crop 8/8.
  - `WanVideoEncode` of the 1280×736 still is /16-clean (no internal resize), so its latent is 46×80 with T=1. That matches the `noise[:, 0:1]` insert.
  - Frames 97 = 4·24+1 and 17 are valid.
  - The HG-2 linear floor at the *generated* 1280×736 is ≈1504 s. The plan's 1472 s is computed at 720. The measured gate supersedes both.

**Step order and dependencies:** Step 0 (venv, worktree, golden, fixture pin) comes before every consumer. Step 5 reads INPUT_TYPES before the WAN edits. Step 6 precedes Step 7 (LTX live). Step 8 puts the measurement before the drop-in + fast-forward + restart. J1–J4 gate Step 9. The order is sound. Its only broken input is the Step 0 venv (B-new-1).

**New node and API claims, checked live:**
- **Core `ImageScale`** (`nodes.py:1892`): required inputs are `image`, `upscale_method` (∈ …`lanczos`), `width`, `height`, `crop` (∈ `disabled`/`center`). ✓
- **`WanVideoEmptyEmbeds`**: required `width`, `height` (step 8) and `num_frames` (step 4); optional `extra_latents: LATENT`, which becomes `[{"samples", "index": 0}]`. ✓
- **`WanVideoEncode`** (`nodes.py:2234`): required `vae` (WANVAE), `image`, **`enable_vae_tiling`, `tile_x`, `tile_y`, `tile_stride_x`, `tile_stride_y`**; returns a LATENT. ✓ (the tile inputs are NB-7)
- **5B sampler path:**
  - extra_latents is inserted at latent index 0 (`nodes_sampler.py:764-777`).
  - On the 5B path, clean indices get timestep 0 (`:1846`).
  - The scheduler step skips clean latents when the scheduler is not Pusa (`:2530`). So the current `unipc` scheduler works; Pusa is not required even though the example uses `flowmatch_pusa`. ✓
- **Shipped `5B_I2V_example_WIP` wiring:** `LoadImage → ImageResizeKJv2 → WanVideoEncode → WanVideoEmptyEmbeds.extra_latents → WanVideoSampler.image_embeds`, with the resize's width/height feeding EmptyEmbeds. The plan's chain is the same, with core `ImageScale` replacing the KJ resize. ✓
- **ComfyUI `/interrupt`:** an optional `{"prompt_id": …}` body gives a **targeted** interrupt; with no body it interrupts globally. `POST /queue {"delete":[ids]}` and the `GET /queue` shape are as the plan assumes. ✓ (NB-3)
- **Health interlock vs. the engine:** `localServiceHealthy` runs before `assertLocalOwnerPure` and before any ledger or state write (`cli.mjs`), so a non-2xx refuses at no cost. ✓ It runs **once per command, not before each seed+1 retry**, so 429 is still the in-run backstop, as the plan says.
- **Imports via PYTHONPATH:**
  - `ltx.service` will have PYTHONPATH set to the worktree root, so `import local_media` resolves.
  - The live WAN unit has `Environment=PYTHONPATH=/home/jarvis/Wan2.2`, so `import local_media` resolves after the Step 8 fast-forward. ✓
  - Pytest (no `pythonpath` in `pyproject.toml`; `tests/` has no `__init__`) needs the root on `sys.path` (folded into B-new-1).
- **ffmpeg tail and atomic rename:** LTX ordering is correct (executor → ffmpeg → rename → `completed`), and the pilot output is mp4 + aac, so `-c:a copy` is valid. ✓ The WAN tail is unspecified (NB-2).
- **systemd drop-in:** `wan2.2.service` is a system unit at `/etc/systemd/system/` with no current drop-ins (`DropInPaths=` is empty) and existing `Environment=` lines for PYTHONPATH and `CUDA_VISIBLE_DEVICES=0,1`. A `wan2.2.service.d/*.conf` with `Environment=WAN_JOB_TIMEOUT_SECONDS=… WAN_GPU_IDS=0` is the right mechanism. ✓ (`daemon-reload` is noted in NB-8.)

### B-new-1 — The Step 0 test venv cannot import the wrappers' runtime stack, so the offline suite (including C1's TestClient proofs) cannot run as specified

- **Claim:**
  - §0.7 and Step 0 create `/home/jarvis/.venv/wan2.2-hg2-tests` "with `--system-site-packages` and pytest". §2 relies on "TestClient tests (httpx present)".
  - Every step "ends with its offline tests green in the test venv".
- **Evidence (live peer):**
  - The shared venv's `pyvenv.cfg` is `home = /usr/bin`, `include-system-site-packages = false`, `version = 3.12.3`. fastapi, httpx, pydantic, uvicorn and starlette exist **only** inside that venv.
  - `--system-site-packages` adds the *base* interpreter's dirs (`/usr/local/lib/python3.12/dist-packages`, `/usr/lib/python3/dist-packages`, `/usr/lib/python3.12/dist-packages`). Venvs do not nest, and creating one from the shared venv's python uses `_base_executable=/usr/bin/python3.12`.
  - Neither `/usr/bin/python3.12` nor `/usr/bin/python3` sees any of those five modules. `/usr/bin/python3` now resolves to **3.14.4**, not the 3.12.3 runtime.
  - Result: `wan_service`/`ltx_service` cannot even be imported (they need pydantic and fastapi), and the Step 0 golden capture needs pydantic as well.
- **Why it blocks:** the very first step cannot reach "green" as written. Each obvious workaround breaks something:
  - installing pytest into the shared venv breaks §0.7 and changes ComfyUI's runtime packages;
  - unpinned `pip install fastapi …` into the test venv means testing other versions than the runtime;
  - `python3 -m venv` gives a 3.14 interpreter.

  Each of these quietly weakens C1's proof and the "recorded counts" acceptance.
- **Required amendment (one paragraph in §0.7 + Step 0):** use the runtime interpreter and the exact runtime packages, read-only. Either:
  - (a) create the test venv with `/usr/bin/python3.12 -m venv`, install pytest into it, and add a `.pth` file that appends `/home/jarvis/.venv/wan2.2/lib/python3.12/site-packages`; or
  - (b) run `/home/jarvis/.venv/wan2.2/bin/python -m pip install --target <test-deps dir> pytest` and test with `PYTHONPATH=<test-deps dir>:<worktree> /home/jarvis/.venv/wan2.2/bin/python -m pytest tests/`.

  Never install into `/home/jarvis/.venv/wan2.2`. Pin the exact test command (with the worktree root on `sys.path`), and record the interpreter (3.12.3) and the fastapi/pydantic/httpx versions alongside the counts.

No other executable blocker was found. Sections §1–§9 contain no internal contradiction severe enough to block; the drift items are below.

## Non-blockers

New items only. Fold them into the step packets.

- **NB-1 — conftest isolation is incomplete.**
  - Live `worker.py:32` puts `CALIBRATION_PATH` under `Path.home()`, and `:381` hard-codes `~/.local/share/wan2.2/outputs/{job}.mp4`. Neither follows `WAN_OUTPUT_DIR`.
  - WAN lifecycle tests that reach completion would call `record_runtime` and write fake runtimes into the **live** `calibration.json` that the running service reads, and would drop files into the live outputs directory.
  - Fix: conftest sets `HOME` to a temp dir before imports; the WAN worker writes through `config.OUTPUT_DIR`; add an assertion that the real home directory is unchanged (the hermetic-tests doctrine).
- **NB-2 — the WAN crop tail is not placed.** §4b promises the crop, but the §3 WAN worker row does not list it, and "completed only after rename" is written for LTX only.
  - Put the ffmpeg tail in shared `local_media.py`, so WAN does not import `ltx_service`.
  - Run it in the executor, with rename before `completed` and the expired-job check before publishing.
  - Add an offline WAN-path tail test (exact 1280×720 from a 1280×736 fixture).
- **NB-3 — use ComfyUI's targeted interrupt.** Send `POST /interrupt {"prompt_id": <own id>}`, which the live peer supports, instead of checking `/queue` and then sending a global interrupt. Add a test where a foreign prompt is running and no interrupt is sent.
- **NB-4 — lock placement and `/prompt` call site.**
  - §3 places the `asyncio.Lock` in `worker.py`, but the 429 busy check lives in `main.py` admission. The lock must span the admission check and the slot reservation; `test_interlock` "simultaneous admissions" forces this.
  - State where `/prompt` is called. If it is called in the worker, a `node_errors` 400 becomes job `failed`, not the POST's 4xx.
- **NB-5 — staged copies leak on refusal.** Stills are staged before the busy check, so a 429 or 503 refusal leaks the per-job ComfyUI/input copy. Either run the busy check first or clean up on every refusal, and test it. §2.5 also lacks a test for "copied input removed at terminal state".
- **NB-6 — WAN `/cancel` still breaks the §1/§5 rule.**
  - The current handler sets a lasting `cancelled`, which the adapter reads as `poll_failure`.
  - `_process_loop` then overwrites a queued job's `cancelled` with `processing`, so the job runs anyway.
  - The engine never calls `/cancel`; fix it for operator use and add a cancel-while-queued monotonicity case.
- **NB-7 — the I2V graph must carry every required `WanVideoEncode` input.** It must include `enable_vae_tiling, tile_x, tile_y, tile_stride_x, tile_stride_y` (the example uses False/272/272/144/128), or `/prompt` returns 400. Assert this in `test_wan_i2v_graph.py` against the Step 5 INPUT_TYPES read.
- **NB-8 — Step 8 operational details.**
  - Name the measurement path: the still-live `3a4b80b` wrapper (T2V only, 600 s timeout, legacy lifecycle) at a 32-grid landscape size such as 1280×736, sized to finish well under 600 s. The alternative is direct ComfyUI submission.
  - Add `systemctl daemon-reload` before the restart.
  - An LTX drop-in implies an LTX restart; that is harmless and not covered by the WAN confirmation.
  - Quote the floor at the generated size (≈1504 s) or label 1472 s as computed at 720 rows.

## Direct answer

Not quite. v1.1 closes every round-1 blocker in substance:
- admission comes before the 202, with zero-submission tests;
- stills are read once, hashed, and written exclusively;
- terminal states stay terminal, and only the wrapper's own prompt is interrupted or deleted;
- the WAN and LTX mapping math reproduces 1280×720, the 1088×1920 golden and the runbook precedent with no padding;
- the measured timeout gate and worktree isolation are in place.

The new I2V chain and ComfyUI API claims all match live peer code. One executable defect remains. The Step 0 test venv (`--system-site-packages`) cannot see fastapi, httpx or pydantic, because they live only in the shared venv and the peer's default `python3` is now 3.14. As written, the offline suite, including C1's TestClient proofs, cannot run without breaking the shared-venv rule or testing against the wrong interpreter and versions. Amend §0.7 and Step 0 to use the 3.12 runtime interpreter with the shared site-packages read-only and pytest kept out of the shared venv, plus the exact test command. A text check of that amendment is enough to close it; no new design review is needed. Fold NB-1 through NB-8 into the step packets. After that, v1.1 is ready to execute.
