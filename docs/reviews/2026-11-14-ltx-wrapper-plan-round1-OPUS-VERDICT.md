# OPUS VERDICT — LTX wrapper + WAN upgrade plan (round 1)
Reviewer: Claude Opus 5.5 (`claude-opus-5-5`), Opus seat. Reviewed independently of the GPT seat. Read-only.
Date: 2026-11-14
Sources read:
- **Input and plan files:** `2026-11-14-ltx-wrapper-plan-round1-FOR-GPT-INPUT.md`; `docs/2026-11-14-ltx-wrapper-implementation-plan.md` (full); `docs/2026-11-14-ltx-wrapper-scope.md` (full); `docs/2026-11-14-orchestrator-spec-analysis.md` (full).
- **Engine copies and evidence:** `engine-local-wan.mjs` (full); `engine-local-ltx.mjs` (full); `engine-cli.mjs` (imports, flag checks, `localTestHandler` lines 680–801); `engine-local-services.json`; `engine-clips.json`; `peer-evidence.md` (full).
- **Extra engine reads in the Locksmith APP working tree:**
  - `diff` of the three `.mjs` copies against the tree: identical. The tree is at HEAD `6ede583`; `4d4e4fa` exists in history.
  - `providers/local-config.mjs`: `model` accepts any non-empty string.
  - `jobs.mjs` lines 27, 31, 600–630 and 727 (poll loop and attempt cap); `core/download.mjs` (250 MiB cap, `ftyp`); `core/http.mjs:10`.
- **Local Wan2.2 upstream config:** `wan/configs/__init__.py:46`, `wan/configs/wan_ti2v_5B.py:17,20`.
- **Live peer, read-only over ssh:**
  - `systemctl cat` for `wan2.2.service` and `comfyui.service`; git state.
  - WanVideoWrapper `nodes.py`, `nodes_sampler.py`, `nodes_utility.py`, `wanvideo/modules/model.py`, and the `example_workflows/*5B*I2V*` node lists.
  - ComfyUI `comfy_extras/nodes_lt.py` and `nodes_lt_audio.py`.
  - `RUNBOOK.txt`; `calibration.json`.
  - ffprobe of all 19 earlier WAN outputs; `file` on both staged stills.
  - `GET :8188/queue`; `GET :8765/health`; venv site-packages; `nvidia-smi`.

## Verdict
REVISE BEFORE EXECUTION

## Live-code spot-check lens (mandatory)

**Contract, plan §1 against `engine-local-wan.mjs`: all correct.**
- Job id regex: `:14`, and checked on 202 at `:136`.
- 4xx except 429 is a definite failure; the body's `error` or `detail` is read, sliced to 200 characters: `:82-86` and `:141-143`.
- 429, 5xx, network errors and timeouts are uncertain: `:131-133` and `:144`.
- Status strings: `:155-161`. 404 means `not_found`: `:150`. Any other non-2xx is `poll_failure`: `:151`.
- `fetchOutput` is bounded and checks MP4: `:164-172`. `MAX_VIDEO_BYTES` is 250 MiB with `ftyp` at bytes 4–8 (`core/download.mjs:7,49`).
- No `Authorization` header (`:101`); `redirect:'error'` (`:98`); health means any 2xx (`:199`).
- `seed` is `?? null` (`:64`), but `local-test` always sends an integer: `baseSeed + attempt - 1` (`cli.mjs:758-760`).
- `model_variant` comes from `route.model`. `local-config.mjs` accepts any non-empty string, so `5b-gguf` and `ltx-2.5-q3` are valid.
- **Omitted from §1:** each request has a 60 s timeout (`local-wan.mjs:16,99`). `/generate` must answer within 60 s. A synchronous guard plus submit is well inside that.
- The engine sends a **relative** `image_path` (`locksmith-van-front.png`, `engine-clips.json:9`; `cli.mjs:761`). The wrapper has to join it to its stills root.
- The engine has no deadline shorter than the wrapper's: it polls every 30 s and marks a job stale only after 24 h (`jobs.mjs:604-607`). Ten consecutive poll failures make the job uncertain (`jobs.mjs:27,617`). Attempts are capped at 3 per unit version (`jobs.mjs:31,727`).

**Graph, plan §3 against the Q3 JSON (`peer-evidence.md` lines 627–989): faithful, apart from the coverage gaps in N5.**
- Fixed nodes 1–27 and 31–34 match the plan's description.
- Sigma strings match exactly: node 14 has 9 values (8 steps) and node 25 has 4 values (3 steps).
- I2V strength is 0.7 on node 33, applied to node 8 (the stage-1 empty latent), and 1.0 on node 34, applied to node 22 (the upsampled latent). `LTXVPreprocess` uses 18.
- One shared dual-CFG guider (node 11) runs at 1.0/1.0 for both stages, with `euler_ancestral`. Both `RandomNoise` seeds are 42. `VAEDecodeTiled` uses 256/64/64/16.
- Audio path: 7 → 9 → 10, then 16:1 → 23, then 27:1 → 18 → 19.
- Conditioning `frame_rate` is 24.0; node 9 `frame_rate` is the integer 24. The empty latent is 544×960×121.
- `SaveVideo` uses `format:"auto"` with `codec:"h264"`.
- Node limits (`nodes_lt.py:71-73`): width and height step 32, length step 8. `LTXVImgToVideoInplace` does a bilinear **center crop** of the still to the latent size (`nodes_lt.py:157-166`).

**WAN claims against the worker source:**
- **Correct:**
  - The worker is T2V only; `image_path` is never read.
  - Pydantic drops `image_sha256`.
  - `cfg` is hard-coded to 5.0 (`peer-evidence.md:404`).
  - The job timeout is 600 s (`:16`).
  - `/health` reports `5b-gguf` (`:591`; live `:8765/health` = 200).
  - The I2V node classes are present.
- **Wrong:**
  - The proposed I2V chain does not work on 5B (B2).
  - 1280×720 is not a valid 5B size (B1).

**Mapping math recomputed:**
- **LTX:** 1280×720 → half 640×360 → snapped down to 640×352 → ×2 = 1280×704. 704 is under 720, so the plan's rule **pads 16 rows**; it does not crop (B3). 97 = 8·12+1 is valid.
- **WAN on 5B:** dimensions must be multiples of 32 (`vae_stride 16 × patch 2`). 720/32 = 22.5, so 1280×720 is invalid (B1). 97 = 4·24+1 is valid.
- **WAN production time:** the live `calibration.json` gives 3.2486e-7 s/unit. 97·50·1280·720 = 4.47e9 units, so about 1,472 s (≈24.5 min) is a **linear floor**. The latent sequence is 5× the 17-frame calibration shape, so attention makes the real time longer (B4).
- **LTX HG-2:** about 0.80 (frames) × 0.43–0.47 (pixels) × 290 s ≈ 100–140 s of diffusion plus model loads. The 900 s budget is ample.
- **LTX smoke:** 33 frames with "~1–2 min" is plausible.

**Live peer state:**
- `/home/jarvis/Wan2.2` is at `3a4b80b` on `main`, clean; there is no `hg2-wrappers` branch yet.
- The ComfyUI queue is empty.
- `ComfyUI/input` is owned by `jarvis` with mode 775.
- Both stills are 2,580,316 B, mode 0600, owned by `jarvis`, and **941×1672 portrait**.
- ffmpeg and ffprobe are in `/usr/bin`.
- **pytest is absent from the venv.** httpx 0.28.1, fastapi 0.143.3, pydantic 2.14.1 and uvicorn 0.54.0 are present.
- **GPU1 (0000:0B:00.0) currently reports "Unknown Error"**; `nvidia-smi -L` lists only GPU 0 (N12).

## Blockers

**B1 — WAN cannot serve the clip set's 1280×720 on TI2V-5B, the plan has no WAN size mapping, and the Step 8 smoke never tests the HG-2 shape.**
- **Plan:** §2 changes only stills, I2V, cfg and variant handling for WAN, and claims the T2V path is "byte-identical". Step 8 smokes at "17 frames, 704×1280". Step 9 then runs the clip set at 1280×720.
- **Evidence:**
  - TI2V-5B supports only `704*1280` and `1280*704` (`wan/configs/__init__.py:46`). Its `vae_stride` (4,16,16) and `patch_size` (1,2,2) (`wan_ti2v_5B.py:17,20`) require multiples of 32.
  - On the peer, `WanVideoEmptyEmbeds` gives latent height `height//8` = 90 (`nodes.py:1430-1433`). The sampler halves that for 5B to **45, which is odd** (`nodes_sampler.py:337-340`).
  - The stride-2 `patch_embedding` (`model.py:1874`) produces 22 patches, and `unpatchify` gives back 44 rows, not 45 (`model.py:3410-3430`).
  - All 19 earlier WAN outputs ffprobe as 704×1280×17. 1280×720 has never run.
  - This comes from reading the code, not from a run, but I expect a shape mismatch with high confidence.
- **Why it blocks:** the WAN HG-2 take fails. The engine retries up to 3 attempts, which exhausts the unit version. The smoke passes anyway, so nothing catches it before HG-2.
- **Required amendment:**
  - Add a WAN size mapping onto the 32-px grid, with an exact-size ffmpeg step afterwards. Either generate 1280×736 and center-crop 8 px per side, or generate 1280×704 and scale up uniformly then crop the width. **Never pad black.**
  - Apply the same size to the I2V still resize, and add a mapping test.
  - Run the Step 8 smoke at a **1280×720 request** (small frame and step counts).
  - Limit the "T2V byte-identical" claim to the proven 704×1280 shape.

**B2 — The §2 WAN I2V chain is the 14B channel-concat path and crashes on 5B. The plan's own Step 5 gate already fails.**
- **Plan:** §2 specifies `LoadImage → WanVideoImageResizeToClosest → WanVideoImageToVideoEncode` feeding the sampler's `image_embeds`.
- **Evidence (peer):**
  - `WanVideoImageToVideoEncode` returns `{image_embeds: y, mask}` (`nodes.py:985-1140`).
  - When `in_dim` is 48 (5B), the sampler skips the mask and passes `y` as `image_cond` (`nodes_sampler.py:228-241`). 5B is detected through `out_dim == 48` (`:112`).
  - The model then does `x = cat([x, y], dim=0)` (`model.py:2444-2450`), giving 96 channels to a patch embedding built for 48 (`:1874`).
  - The 5B I2V path is `extra_latents` instead: see `nodes_sampler.py:753` ("extra latents (Pusa) and 5b"), `:1824` (`is_5b … clean_latent_indices`), and `WanVideoEmptyEmbeds.extra_latents` (`nodes.py:1411-1446`).
  - The shipped `wanvideo_2_2_5B_I2V_example_WIP.json` uses `LoadImage → ImageResizeKJv2 → WanVideoEncode → WanVideoEmptyEmbeds → WanVideoSampler`. It never uses `ImageToVideoEncode`.
  - `ImageResizeKJv2` comes from KJNodes, which is **not installed**.
  - `WanVideoImageResizeToClosest` rounds to multiples of 16 (`nodes_utility.py:47-54`), which is not safe for 5B.
- **Why it blocks:** §2 and the test names describe a chain that will fail at sampling. The plan itself says to amend before coding.
- **Required amendment:**
  - Rewrite the chain now: `LoadImage` (the copied still) → core `ImageScale` (lanczos, the B1 size, `crop:"center"`) → `WanVideoEncode` (vae from node 2) → `WanVideoEmptyEmbeds(width, height, num_frames, extra_latents)` → node 6 `image_embeds`.
  - T2V keeps node 5 unchanged.
  - Keep the Step 5 `INPUT_TYPES` read as a check.
  - Upstream marks the example as WIP, so the Step 8 visual check of still fidelity is the real proof.

**B3 — The LTX size rule rounds down, which contradicts the precedent it cites and the plan's own test and acceptance text. The only HG-2 clip falls on the black-pad branch.**
- **Plan says three different things:**
  - §3: "snapped DOWN … crop/pad (runbook crop precedent; … pad black if under)".
  - §2 test row: "1280×704 → crop 1280×720".
  - Step 7: "verify exact-res crop on a 1280×720 request".
- **Evidence:**
  - From 704 rows, reaching 720 needs 16 **added** rows. You cannot crop up, so the test and acceptance as written cannot be met. The implemented result would be 8 px black bars top and bottom.
  - The runbook precedent rounds **up**. It targets 1080×1920, diffuses at 544×960 (540 rounded up to 544), then crops 4 px per side (RUNBOOK lines 19 and 27).
  - Under the plan's round-down rule, 1080×1920 would become 512×960 → 1024×1920, with 28 px black bars on each side. The rule does not reproduce its own precedent.
- **Why it blocks:** the spec contradicts itself, the acceptance check cannot pass as written, and the visible default is a letterboxed review clip.
- **Required amendment:**
  - Round stage-1 dimensions **up** to /32: 640×384 → 1280×768, then center-crop 24 rows per side. This still reproduces the 1088×1920 golden.
  - Never pad, and fix the §2 test row and the Step 7 text.
  - Cost: about 9% more stage-2 pixels. That is far inside the pilot's envelope (95 vs 253 Mpx-frames).

**B4 — The WAN HG-2 run at the fixed clip settings will time out, and the timeout path leaves orphaned ComfyUI prompts that later block LTX.**
- **Plan:** §5 offers "smaller params (Jose's decision)" or raising the timeout through env, and Step 9 runs the fixed clip set as is.
- **Evidence:**
  - The clip set is 97 frames × 50 steps at 1280×720 (`engine-clips.json:13-19`), against a 600 s timeout. The ≥24.5 min floor is computed above.
  - "Smaller params" conflicts with D4 and §0.1, which keep the clip set unchanged.
  - When the `wait_for` timeout fires, the job is marked failed, but the executor thread keeps running `_run_generation` (`peer-evidence.md:464-475`). That thread can later overwrite the status to "completed" (`:549-567`).
  - Neither timeout path calls `interrupt()` or removes the queued prompt (`:470-472`, `:575-577`).
  - The engine then retries with seed+1, up to 3 attempts (`cli.mjs:778-795`). Each new prompt waits behind the orphan, spends its 600 s and times out, so the orphans pile up.
  - When Jose then runs `--route local-ltx`, the planned interlock sees a busy queue, returns 429, the take becomes uncertain, and it needs `--recover`.
- **Required amendment:**
  - (a) Make the timeout raise part of Step 8: a drop-in setting `WAN_JOB_TIMEOUT_SECONDS`, and likewise for LTX. Derive the value from a measured landscape run (at least 2× the extrapolated time), installed together with the restart Jose confirms. Remove the "smaller params" option, or hand it to Jose explicitly as a clip-set change.
  - (b) In both wrappers, on timeout or cancel, call ComfyUI `POST /interrupt` if the prompt is running, or `POST /queue {"delete":[id]}` if it is pending. Make terminal states final, and test this with the fake client.

**B5 — The build happens in the working tree the live service runs from, so the "old code until the confirmed restart" guarantee and the independent rollbacks are both false.**
- **Plan:** §0.4 says "work on branch `hg2-wrappers` … running WAN keeps old code until the confirmed restart". The Rollback section says "LTX = stop/disable (no WAN impact). WAN = `git checkout main`".
- **Evidence (live unit file):** `wan2.2.service` has `WorkingDirectory` and `PYTHONPATH` set to `/home/jarvis/Wan2.2`, plus `Restart=on-failure`, `RestartSec=10` and `WantedBy=multi-user.target`.
- **Consequences:**
  - Any crash or reboot during Steps 1–7 restarts WAN on the half-built branch without Jose's confirmation, which breaks §0.3 and the operator policy.
  - `git checkout main` for a WAN rollback removes `ltx_service/` and `local_media.py` from the tree that `ltx.service` runs from, so LTX fails on its next restart. The two rollbacks are not independent.
- **Required amendment:**
  - Build in `git worktree add /home/jarvis/Wan2.2-hg2 -b hg2-wrappers` and point `ltx.service` at that worktree.
  - Leave `/home/jarvis/Wan2.2` on `main` until Step 8, when WAN moves by fast-forward plus a restart Jose confirms.

## Non-blockers

**N1 (medium) — The interlock only works in one direction, can race, and makes `MAX_QUEUE_DEPTH=4` dead config.**
- WAN has no check on whether ComfyUI is busy. Its 429 only fires when its own queue size reaches 10 (`peer-evidence.md:121-126,610-613`).
- WAN runs two `GpuWorker`s (GPU ids "0,1", `:17,602-603`) that both submit to one ComfyUI.
- In LTX, the check and the submit are separate steps with no lock between them.
- For the check to return 429, it must sit in the request path. §2 puts it in `worker.py`.
- Fixes:
  - Put an `asyncio.Lock` around the check and submit, and add the same check to WAN.
  - Set `WAN_GPU_IDS=0` in the Step 8 drop-in.
  - Set LTX queue depth to 1 or remove it.
  - Narrow §5's "mitigated by the interlock" claim.

**N2 (medium) — WAN validation runs in the wrong place.**
- §2 puts the stills guard and the variant check in `worker.py`, but WAN builds the graph after it has already returned 202 (`:521-531`). These errors would show up as failed polls instead of §1's definite 4xx, and `main.py`'s 400 mapping would never fire.
- Fix: run both checks in `main.py` before `pool.submit`, and add HTTP-level tests with TestClient (httpx is present).

**N3 (medium) — There are now three variant settings.**
- The existing ones are `WAN_MODEL_VARIANT="5b"` (`:10`) and the schema default `"5b"` (`:38`), and `/health` hard-codes `5b-gguf` (`:591`).
- With strict checking against a new `SERVED_VARIANT`, a request that leaves out `model_variant` gets a 400. That breaks "T2V unchanged" for callers other than the engine.
- Fix: let one setting drive the schema default, the check and `/health`, and add a regression test for a bare T2V request.

**N4 (low-medium) — Error status mapping.**
- FastAPI's default validation response is 422 with a list `detail`, which the engine records as `local_provider_failed` (`local-wan.mjs:82-86`). The 400 `{error, detail}` the plan wants needs a `RequestValidationError` handler.
- A ComfyUI `/prompt` 400 (`node_errors`) means nothing was queued, so it is definite. Map it to a definite 4xx, not 503. Keep 503 for connection failures and timeouts.

**N5 (medium) — LTX parameter coverage.**
- `num_frames` must drive both node 8 `length` **and** node 9 `frames_number`.
- fps must drive nodes 5, 9 and 19.
- The node 31 filename must be a parameter.
- The test's list of fields that vary leaves out frames and the image name. A golden test at 121 frames and 24 fps cannot catch a node 9 that stays fixed.
- The golden comparison should use the `prompt` object, because the fixture has a top-level `client_id`. Pin the fixture by sha256 to the runbook's JSON on the peer.

**N6 (medium) — Details for the stills guard.**
- Check containment with `resolved.is_relative_to(root.resolve())`. A string-prefix check lets `/home/jarvis/wan-stills-x` through.
- Require a regular file.
- Read the file once, hash it in memory, and write those same bytes with `open(dst,'xb')`. That closes the gap between validate and copy and prevents overwriting.
- Sanitize the basename to `[A-Za-z0-9._-]`; ComfyUI gives `name [output]` and subpaths special meaning.
- LTX must require `image_path`, because the proven graph is I2V only.
- Test the relative-path join, and clean up copied inputs when the job reaches a terminal state.

**N7 (medium) — Test setup order and venv.**
- pytest is absent, but §4 needs green tests from Step 1 while the install only happens at Step 6.
- The venv is also `comfyui.service`'s runtime, so installing into it changes the live generator's environment.
- Fix:
  - At a new Step 0, create a separate test venv with `--system-site-packages`.
  - In `conftest`, point `WAN_OUTPUT_DIR` at a temp dir, because `config.py` runs `mkdir` at import.

**N8 (low) — The T2V golden must come from the unmodified code.** Capture it from `build_wan22_workflow` at `3a4b80b` with a fixed seed before any edit. A `None` seed is random (`:349-350`).

**N9 (low-medium) — LTX worker behavior.**
- Keep blocking calls and ffmpeg in an executor so `/status` stays responsive under the 30 s poll and 60 s timeout.
- Set `completed` only after ffmpeg finishes and the file has been atomically renamed into place. Otherwise `/output` fails and the take ends up needing a reconcile.
- Use ffmpeg `-c:a copy`.

**N10 (low) — `ltx.service` template.** Set `User=jarvis` (the stills are mode 0600), `WorkingDirectory` and `PYTHONPATH`, mirroring `wan2.2.service`.

**N11 (medium, for Jose — his files, not wrapper code).**
- The staged still is **941×1672 portrait**, but the clip is 1280×720 landscape. A center crop to 16:9 keeps only the middle band, about 941×529 px or roughly 32% of the height (`nodes_lt.py:165-166`).
- The still's sha256 matches the pilot reference, whose pilot prompt describes "the woman … by the white SUV". Both clip prompts describe a locksmith van. I could not view the image, so this is unverified. Jose should look at it before HG-2.

**N12 (observation, live peer).** GPU1 reports "Unknown Error" and only GPU 0 is listed; uptime is 15 h 48 m. ComfyUI's single-GPU path on GPU0 is not affected. Check the hardware before the live smokes.

## Missed opportunities
- **Use `/health` as the main interlock.** Return non-2xx when ComfyUI `/system_stats` fails or `/queue` is not empty. The engine then refuses at its health gate before writing anything to the ledger (`cli.mjs:733-736`). That costs no attempt and needs no `--recover`, unlike a 429. Keep the 429 as the backstop.
- **Pre-flight before each Step 9 route:** confirm `:8188/queue` is empty and run `nvidia-smi`.
- **Calibrate the B4 timeout from a measured mid-size landscape WAN run during Step 8,** instead of the linear extrapolation.

## Direct answer
The plan is not executable as written. It pins the engine contract correctly, every check against the adapter passes, and it copies the proven Q3 graph accurately. The WAN half has two confirmed design defects:
- The frozen 1280×720 size is not valid on TI2V-5B (B1).
- The proposed I2V chain is the 14B channel-concat path, which crashes on 5B; the working path is `WanVideoEncode` → `extra_latents` (B2).

The Step 8 smoke runs at 704×1280, so it would pass and still hide both. Three more problems would turn HG-2 into a failure or a defect:
- The LTX size rule rounds down, which letterboxes the only clip and contradicts its own crop precedent (B3).
- The WAN 600 s timeout fails at the frozen settings, and its timeout path leaves orphaned ComfyUI prompts that pile up and then block the LTX run with 429s (B4).
- Building inside the live service's working tree breaks the restart-confirmation gate and couples the two rollbacks (B5).

All five are cheap amendments to the plan text and design, and none needs an engine or ComfyUI change. Once they are applied, along with the N1–N7 fixes to placement and tests, the plan looks safe to execute.
