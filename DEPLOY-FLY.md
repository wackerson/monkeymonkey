# Fly.io deployment

The included `Dockerfile` builds the complete local processor inside a Linux image: Python 3.12, FFmpeg/PyAV, Rubber Band, and the server-side Fal Node client. Models remain hosted APIs, so this deployment does not need a GPU.

## Design

- One private FastAPI Machine runs the UI and the background preparation/collection threads.
- A Fly Volume is mounted at `/data`, where the app keeps source uploads, previews, masks, request IDs, and job status. A single Machine is required because Fly Volumes are local to the attached Machine.
- `auto_stop_machines` is intentionally off. A depth/SAM or video generation job must not be interrupted just because the browser is idle.
- `APP_ACCESS_TOKEN` protects the UI and all job/media routes. Keep `FAL_KEY` and the access token in Fly secrets, never in `fly.toml` or `.env` committed to Git.

## First deployment

1. Install and authenticate the Fly CLI, then choose a globally unique `app` name in `fly.toml`. Windows is sufficient: Fly builds this Linux container remotely, so neither Docker Desktop nor local Ubuntu is required.
2. From this directory, create the app and its 20 GB volume in the same region. The value in `fly.toml` must exactly match `YOUR_APP_NAME`:

   ```bash
   fly apps create YOUR_APP_NAME
   fly volumes create genjustsu_runs --app YOUR_APP_NAME --region ord --size 20
   ```

3. Create a long random access token and configure secrets. Fal handles Demucs, depth, SAM 3, and both Seedance stages. Do not put either value in `fly.toml`.

   ```bash
   fly secrets set --app YOUR_APP_NAME FAL_KEY=... APP_ACCESS_TOKEN=...
   ```

4. Deploy with Fly's remote builder (this works without local Docker or Ubuntu):

   ```bash
   fly deploy --remote-only
   ```

5. Verify the service and open it:

   ```bash
   fly status --app YOUR_APP_NAME
   fly checks list --app YOUR_APP_NAME
   fly open --app YOUR_APP_NAME
   ```

Use the deployed URL, enter `APP_ACCESS_TOKEN`, and then use the workflow normally. Delete job directories after delivery because the volume holds private media and provider metadata.

## Test deployment checklist

- Use a short non-sensitive clip first (the app permits up to 30 seconds).
- Confirm the `/health` check is passing before uploading a clip.
- Keep the single Machine running while a job is working. The deployment deliberately disables auto-stop because background preparation and Fal polling run inside that Machine.
- Do not run a second Machine: the job queue is in memory and the Fly Volume is attached to one Machine.

## Before opening it to other users

This is intentionally a private, single-user Machine. A multi-user product needs real user authentication, per-user object storage, a durable database/queue, upload size limits, background-worker isolation, billing controls, and scheduled deletion.
