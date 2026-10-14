# Genjustsu Fal full workflow

This local application retains the original workflow's processing stages:

1. Extract the source soundtrack and use Fal Demucs to isolate vocals.
2. Pitch vocals +3 semitones with Rubber Band without changing duration.
3. Normalize the video, generate coloured depth, then get per-frame SAM 3 masks.
4. Composite the depth subject over the original background and require a full-clip review approval bound to the current artifacts.
5. Embed only the pitch-shifted vocals in the prepared video and submit it with identity references to Fal Seedance Reference-to-Video.
6. Download the generated result, discard its audio, and mux in the untouched original source audio.
7. After an explicit approval, submit the same approved Fal input again with 1080p resolution. Fal has no provider-side draft-completion endpoint, so this is a new billed request—not an upscaling operation.

## Keys and prerequisites

The full depth/SAM/audio workflow needs only `FAL_KEY` in `.env`. No public media host or cloudflared tunnel is needed: the server uploads inputs to Fal storage and polls Fal locally.

The upstream workflow is Bash-first. On this native Windows host, install WSL2 with Ubuntu, then inside WSL install Python 3.12+, Node 20+, and Rubber Band before running `bash setup.sh`. This creates `.venv`, installs Python dependencies and the server-side Fal bridge. Start the UI with `bash start.command` and visit `http://127.0.0.1:8770`.

Do not submit a paid draft until the prepared input has been reviewed end to end. The 1080p approval is separately billed.
