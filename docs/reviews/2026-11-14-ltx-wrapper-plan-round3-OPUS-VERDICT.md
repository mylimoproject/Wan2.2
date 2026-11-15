# OPUS VERDICT — LTX wrapper + WAN upgrade plan (round 3 text check)
Reviewer: Claude Opus 5.5 (`claude-opus-5-5`), Opus seat. I worked independently of the GPT seat and read-only: no files were written, nothing was committed and nothing was pushed.
Date: 2026-11-14
Sources read:
- `docs/reviews/2026-11-14-ltx-wrapper-plan-round3-FOR-GPT-INPUT.md`
- `docs/2026-11-14-ltx-wrapper-implementation-plan.md` v1.2, read in full. Its sha256 is `756e6915f09c38dd4f370a16f8eb4c23ccaab6b2220e5619da030b2950dfa147`.
- `reviews/2026-11-14-ltx-wrapper-plan-round2-GPT-VERDICT.md` and `…-round2-OPUS-VERDICT.md`, both read in full.
- Local HEAD is confirmed as `4b791dbfb940792178b8287fd5501bbf732fe9ae`.
- The local `tests/` holds only `README.md` and `test.sh`.

## Verdict
APPROVE

## C9 landing
**CLOSED.** Every element of GPT B-new-1's required amendment, and of Opus NB-3, appears in §5 and §2.4. Each requirement below is followed by the landed text that meets it.

- **Targeted interrupt in both wrappers.** §5 is headed "Both wrappers:" and says: "`POST /interrupt` with JSON **`{"prompt_id": <own_comfy_prompt_id>}`** and Content-Type application/json — the live ComfyUI server checks the id against running entries and skips interruption when absent".
- **Never global, never a fallback.** "**Never send an empty-body/global interrupt; never fall back to one** when ownership is absent, changed, or uncheckable. A check-then-act preflight is NOT the invariant: between a `/queue` check and a global interrupt the queue can advance to the other wrapper's prompt."
- **Pending prompt: delete by id, then re-read.** "Pending owned prompt: `POST /queue {"delete":[id]}`, then **re-read queue/history** — a 200 does not prove removal, and the prompt may have moved to running; if running, use the same targeted interrupt."
- **Draining ownership.** "the failed job keeps its slot and its input snapshot until the owned prompt is actually absent/terminal AND the executor has quiesced; a deletion/interrupt HTTP 200 alone never frees the slot or deletes the input. Monotonic failed status; no late output publication."
  - §2.4 mirrors this: "Clean copied inputs when the job reaches a terminal state **and its owned ComfyUI prompt is absent/terminal and the executor quiesced**".
- **Regression tests.** "**own-running→other-running between check and action (assert the exact interrupt JSON, zero global interrupts, no foreign-prompt action)**; **own-pending→own-running before delete**; delete/interrupt no-op or transport failure; no known prompt id; retained ownership/input while draining; own-prompt cleanup before next-job handoff; **cancel-while-queued never revived by the process loop**".
  - §3 assigns these to `test_lifecycle.py`: "§5 regressions incl. the C9 queue-transition cases and cancel-while-queued".
- **No leftover old pattern.** The only `interrupt` mentions in the plan are at lines 94, 95, 97 and 117. None of them keeps the v1.1 "check `/queue` → `POST /interrupt`" wording.

## C10 landing
**CLOSED.** Every element of Opus B-new-1 option (a), and of GPT N-new-1, appears in §0.7, Step 0 and §8.

- **Interpreter.** "create `/home/jarvis/.venv/wan2.2-hg2-tests` with **`/usr/bin/python3.12 -m venv`**". The plan explains the reason: "the peer's default `python3` is now 3.14.4 and sees none of them". It also states that "`--system-site-packages` does NOT expose them".
- **pytest only, and a read-only `.pth`.** "install **pytest only** into it, and add a `.pth` file appending `/home/jarvis/.venv/wan2.2/lib/python3.12/site-packages` **read-only**. **Never install into the shared venv.**"
- **Pinned command.** "`cd /home/jarvis/Wan2.2-hg2 && WAN_OUTPUT_DIR=<tmp> LTX_OUTPUT_DIR=<tmp> /home/jarvis/.venv/wan2.2-hg2-tests/bin/python -m pytest tests/` with the worktree root on `sys.path` (pytest `pythonpath` ini or conftest)".
- **Preflight and recorded versions.** "Step 0 runs an import/collection preflight (both wrappers importable, env vars set before import) and records the interpreter (3.12.3) and the fastapi/pydantic/httpx versions **with their import origins** alongside pytest's version."
- **Step 0 restates it.** "**`/usr/bin/python3.12 -m venv`**, pytest only, read-only `.pth` to the shared site-packages; import/collection preflight with both output-dir env vars set; record interpreter + fastapi/pydantic/httpx versions and origins + pytest version".
- **Wired into the rest of the plan.**
  - The §6 header says: "each step ends with its offline tests green under the §0.7 pinned command".
  - §8 says: "Offline suite green under the pinned §0.7 command (recorded interpreter/versions/counts)".
  - GPT's "if absent, install only into the test env" is covered more strictly: nothing but pytest is installed anywhere.

## Non-blocker presence
- **NB-1:** present. The §3 `conftest.py` row reads "**HOME set to a temp dir before imports** … asserts the real home is unchanged — NB-1". The §3 WAN worker row reads "**all output writes through `config.OUTPUT_DIR`**".
- **NB-2:** present. §2 has the "Shared media tail (round-2 NB-2)" paragraph: tail in `local_media.py`, executor, rename before `completed`, expired-job check, and fixture tests for WAN 1280×736→1280×720 and for LTX.
- **NB-3:** present, merged into C9 above.
- **NB-4:** present. §2 says "An `asyncio.Lock` in `main.py` spans the busy-check **and the slot reservation** (round-2 NB-4)" and "`/prompt` is called **in the worker**".
- **NB-5:** present. §2 says "**stills acceptance last** (so a refusal never leaks a staged copy — round-2 NB-5…)". The tests include "no leaked input copies on refusal" and "copied input removed at terminal state".
- **NB-6:** present. §1 says `/cancel` reports "`failed` with error `cancelled`, never a lasting `cancelled` status". §5 has the cancel-while-queued test, and the §3 WAN `main.py` row has "`/cancel` monotonic".
- **NB-7:** present. §4b lists "`enable_vae_tiling:false, tile_x:272, tile_y:272, tile_stride_x:144, tile_stride_y:128`". §3 `test_wan_i2v_graph.py` "asserts ALL required `WanVideoEncode` inputs incl. the five tile scalars", and Step 5 confirms them through `INPUT_TYPES`.
- **NB-8:** present. Step 8 covers all four points:
  - the measurement path, "through the still-live 3a4b80b wrapper (T2V, 600 s timeout) … or direct ComfyUI submission";
  - "**`systemctl daemon-reload`**";
  - the LTX restart note;
  - "≈1504 s (the 1472 s figure was computed at 720 rows…)".
- **GPT N-new-2:** present. The v1.1 entry is marked "superseded by round-2 independent review (GPT N-new-2…)". The v1.2 entry carries the actual tallies (GPT 30/3/0, Opus 32/1 of 33) and the reviewed v1.1 hash `3709ba4c…`. Its own label is "APPROVED pending the narrow round-3 text-check closure", which is not a self-approval.

## Amendment-introduced contradictions
None of these blocks execution. Each one fails loudly (an import error or a failing test), has only one safe reading, and weakens no guarantee if resolved. By round 2's own standard, they belong in the step packets:

1. **The Step 0 preflight is scoped beyond what exists at Step 0. This comes from C10.**
   - §0.7 asks Step 0 to prove "both wrappers importable", but `ltx_service` is only created at Step 2 and `local_media` at Step 1.
   - If the peer's `tests/` matches the local one (no pytest modules), the pinned `pytest tests/` also exits 5 ("no tests collected") at Step 0.
   - §6 Step 0 itself says only "import/collection preflight", so the two places disagree.
   - Packet fix: at Step 0, import fastapi, pydantic, httpx, starlette and `wan_service` with the env vars set, record their origins, and accept an empty collection. Add `local_media` and `ltx_service` to the import check at the step that creates each one.
2. **§2.5's test wording is looser than §2.4. This comes from C9 and NB-5.**
   - §2.5 says "copied input removed at terminal state". Read literally, that conflicts with §5's "retained ownership/input while draining" for a timed-out job, which is terminal (`failed`) but still draining.
   - Packet fix: write that test to §2.4's condition: terminal AND owned prompt absent or terminal AND executor quiesced.
3. **The "zero global interrupts" assertion is attached to only one test case. This comes from C9.**
   - The assertion sits in the parenthetical of the own-running→other-running case.
   - It should hold in every §5 lifecycle case, especially "no known prompt id" and "transport failure", which are the cases where a fallback would appear.
   - The rule in §5 already forbids the fallback, so this is a test-coverage note, not a conflict.
4. **Minor wording.**
   - The §3 WAN `main.py` row's "`/cancel` monotonic (failed/cancelled…)" should be read as §1 pins it: status `failed`, error `cancelled`.
   - The Step 0 preflight should also assert that fastapi, pydantic and httpx import from `/home/jarvis/.venv/wan2.2/lib/python3.12/site-packages` and not from a user site. In round 2, GPT found user-site copies that a bare `python3.12` can see.

## Direct answer
Yes: v1.2 closes C9 and C10 as both round-2 seats required and contains all the round-2 non-blockers. It is executable from Step 0, provided the four packet notes above go into the Step 0, Step 4 and Step 5 packets and no further consensus round is held.
