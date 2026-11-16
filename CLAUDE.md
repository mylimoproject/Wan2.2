# Wan2.2 — local video harness

Jose's fork of `github.com/mylimoproject/Wan2.2`. A zero-cost implementation and test harness for the Locksmith ads pipeline. Real ads are made on a paid API model, so do not tune this box for production throughput or final-output quality.

Read `NEXT_SPRINT.md` first: it holds the current state, the open `JOSE:` items and what comes next.

## Where things run (this machine, jarvis-rog-x570)

| Service (system unit) | Port | Runs from |
|---|---|---|
| `wan2.2.service` (WAN wrapper, `5b-gguf`) | 8765 | `~/Wan2.2` (this checkout, `main`) |
| `ltx.service` (LTX-2.5 wrapper) | 8767 | `~/Wan2.2-hg2` (worktree, `hg2-wrappers`) |
| `comfyui.service` | 8188 | `~/ComfyUI` |

All three use the venv `~/.venv/wan2.2`. Port 8766 belongs to command-post's API; LTX moved to 8767 by Jose's ruling. Unit drop-ins live in `/etc/systemd/system/*.service.d/`, and the repo copies are in `systemd/`.

Editing files in `~/Wan2.2` or `~/Wan2.2-hg2` changes the code the live services run on their next restart.

## Rulings

- Implementation and test harness only (Jose, 2026-10-18).
- One video-generator service at a time (Jose, 2026-11-01). The dual-GPU orchestrator is a gated future track (`docs/2026-11-14-orchestrator-spec-analysis.md`).
- Live smokes, `--execute` takes and service restarts are Jose's alone. Agents build and test offline.
- The build stays single-GPU on GPU0 by policy.

## Tests

Pinned command (plan §0.7 in `docs/2026-11-14-ltx-wrapper-implementation-plan.md`):

```bash
cd /home/jarvis/Wan2.2-hg2 && WAN_OUTPUT_DIR=<tmp> LTX_OUTPUT_DIR=<tmp> /home/jarvis/.venv/wan2.2-hg2-tests/bin/python -m pytest tests/
```

The test venv holds pytest only and reads the shared venv's packages read-only. **Never install anything into `~/.venv/wan2.2`**: it is ComfyUI's runtime. Offline tests only; never start a generation job as a test.
