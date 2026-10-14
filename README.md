# Genjustsu Fal — full local workflow

This is a local, single-user video subject-replacement workflow adapted from the open-source Genjustsu project. It retains the complete preparation and quality gate:

1. Extract the untouched original soundtrack.
2. Isolate vocals with Fal Demucs, then pitch them +3 semitones with Rubber Band while preserving timing.
3. Normalize source footage to 24 fps, generate coloured depth with Fal Video Depth Anything, and run Fal SAM 3 to make raw frame masks.
4. Composite the masked depth subject over the original background; review the complete clip and approve the exact artifacts before any paid generation.
5. Upload the prepared input and character reference(s) to Fal storage, then submit a Fal Seedance reference-to-video draft.
6. Download the result, discard its generated audio, and mux in the complete original source audio.
7. On a separate explicit approval, submit the saved inputs again to Fal at 1080p and restore the original audio again.

## Provider configuration

Fal provides every hosted model in this workflow: Demucs, Video Depth Anything, SAM 3, and Seedance. Copy `.env.example` to `.env` and set:

```text
FAL_KEY=your_fal_key
```

Fal does not provide an Enhancor-style “complete draft” API. The 1080p action is clearly labeled in the UI because it is a new paid request using the stored, approved inputs and prompt.

## Windows setup

This upstream workflow uses Bash. On a native Windows machine, install WSL2 with Ubuntu first, then in WSL install Python 3.12+, Node 20+, and Rubber Band. From this folder run:

```bash
bash setup.sh
bash start.command
```

Open `http://127.0.0.1:8770`. `setup.sh` creates the Python environment, installs the Python preprocessing dependencies and installs the server-side Fal Node bridge. No Cloudflare tunnel, webhook, or public media host is required.

Never submit a draft until the mask/mesh review is complete. Runs are saved under `runs/` and contain private media plus provider request IDs; do not share them.

## Fly.io

The repository includes a Linux `Dockerfile`, `fly.toml`, private access-token gate, and persistent `/data` run storage for a single-Machine Fly deployment. It includes the depth/SAM/pitch-shift workflow and the optional face-mesh modes, so you do not need Ubuntu, Docker Desktop, or WSL on your Windows laptop when you deploy using Fly's remote builder. Follow [DEPLOY-FLY.md](DEPLOY-FLY.md) for the deployment sequence and security limits. Do not deploy it publicly without the access token.
