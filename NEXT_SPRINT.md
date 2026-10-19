# NEXT_SPRINT — Wan2.2 (local video)

Last updated: 2026-10-19 (tracker created; no code or service change this session)

**What this is.** Jose's fork of `github.com/mylimoproject/Wan2.2`, used as a zero-cost **implementation and test harness** for the Locksmith ads pipeline. Real ads are produced on a paid API model: do not optimize this box for production throughput, and do not tune quality for final output.

**Where it runs.** The serving stack is on the peer **jarvis-rog-x570** (Tailscale `100.105.156.94`), not on jarvis-sister. This checkout is the source clone only; `systemctl --user` on the sister reports `wan2.2` and `comfyui` as not-found, which is expected and not a fault.

**State (verified 2026-10-18; not re-verified since).** FastAPI wrapper on `:8765` and ComfyUI on `:8188`, both enabled and active on the peer after the systemd cutover. The 5B GGUF pipeline is verified end-to-end (FastAPI → ComfyUI → MP4, 17 frames at 704×1280). Progress and ETA were fixed on the peer (`fc0f21c`, `3a4b80b`), and moving T5 to the GPU took a 17f × 10-step job from 329 s to 61 s. The dominant remaining cost is the tiled VAE decode plus h264 save tail (~45 s). Durable detail, model paths and the test recipe live in memory `project_wan22_local_video`.

**Divergence.** This sister clone is on `main`, **1 commit ahead** of `origin/main` (`a9c6c66 docs: session end 2026-10-18 — add Wan2.2 session guide HTML`), never pushed. The peer's copy is separately ahead by 2 (the progress/ETA commits) and is not pushed either.

**Rulings that constrain this project.** Implementation and test harness only (Jose, 2026-10-18). The second RTX 5060 Ti stays idle by design: a second ComfyUI on `:8189` would roughly double throughput across jobs, not make a single job faster. LoRA training is not needed. The sister's `~/Downloads/WAN2.2` (71 GB) is Jose's to move; do not delete it.

**Next, in order:** 1. Re-verify the peer stack after any reboot or update (`GET :8765/health`, ComfyUI `:8188` returns 200) before the ads pipeline relies on it. 2. When the paid provider lands, add the provider selector to the Locksmith ads engine — as of 2026-10-18 only `local-wan` is wired.

**JOSE:** decide whether this clone's session-guide commit and the peer's two progress/ETA commits should be published to `origin/main`; nothing has been pushed.
