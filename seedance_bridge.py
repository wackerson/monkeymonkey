"""Fal Seedance bridge for the local Genjustsu preprocessing workflow."""
from pathlib import Path
import concurrent.futures
import json
import os
import subprocess
import time

import av
import requests

from audio_workflow import finish_preview, prepare_seedance_video
from config import ROOT, credential, setting

FAST_MODEL = "bytedance/seedance-2.0/fast/reference-to-video"
STANDARD_MODEL = "bytedance/seedance-2.0/reference-to-video"


def _bridge(action, payload):
    """Run the Node bridge so FAL_KEY is never exposed to the browser."""
    credential("FAL_KEY")
    result = subprocess.run(
        ["node", str(ROOT / "fal_bridge.mjs"), action], input=json.dumps(payload),
        text=True, capture_output=True, timeout=300, env=os.environ.copy(),
    )
    if result.returncode:
        raise RuntimeError("Fal " + action + " failed: " + (result.stderr.strip() or result.stdout.strip()))
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Fal returned an unreadable response.") from error


def _upload(*paths):
    """Fal storage keeps prepared video and references off third-party media hosts."""
    return _bridge("upload", {"paths": [str(path) for path in paths]})["urls"]


def _model_for(resolution, hd=False):
    if hd or resolution == "1080p":
        return setting("FAL_HD_MODEL", STANDARD_MODEL)
    return setting("FAL_DRAFT_MODEL", FAST_MODEL)


def _duration(video):
    with av.open(str(video)) as source:
        seconds = float(source.duration / av.time_base)
    return str(max(4, min(15, round(seconds))))


def _reference_input(prepared, sirio, tein, prompt, urls, resolution):
    video_urls = [urls[0]]
    if Path(sirio).suffix.lower() in {".mp4", ".mov", ".webm"}:
        video_urls.append(urls[1])
        return "multi_reference", {
            "prompt": prompt + "\n@Video1 is the prepared source edit with isolated vocals pitched +3 semitones. @Video2 is only the replacement character's visual identity reference. Use only @Video1 audio for speech timing and performance.",
            "video_urls": video_urls, "image_urls": urls[2:], "resolution": resolution,
            "duration": _duration(prepared), "aspect_ratio": "auto", "generate_audio": False,
        }
    return "edit", {
        "prompt": prompt.replace("@Audio1", "the audio embedded in @Video1") + "\n@Video1 contains the colored-depth composite and embedded isolated vocals pitched up three semitones, without the music bed; use its embedded audio for performance and lip synchronization. " + ("@Image1 is the primary character reference; @Image2 is the secondary character reference." if tein else "@Image1 is the only replacement character reference."),
        "video_urls": video_urls, "image_urls": urls[1:], "resolution": resolution,
        "duration": _duration(prepared), "aspect_ratio": "auto", "generate_audio": False,
    }


def _request_id(data):
    return data.get("request_id") or data.get("requestId")


def submit(folder, prompt, sirio, tein=None, status=print):
    folder = Path(folder)
    from mask_review import require_approved, is_mesh

    require_approved(folder)
    if (folder / "seedance-response.json").exists():
        raise ValueError("This job already has a provider response. Resume it; prepare a new job for a deliberate variation.")
    if not (folder / "audio-manifest.json").exists():
        raise ValueError("Audio separation must complete before submission.")
    status("Pitching isolated vocals +3 semitones and embedding in colored-depth video")
    prepared = folder / "seedance-input.mp4" if is_mesh(folder) else prepare_seedance_video(folder)
    status("Uploading prepared input and character references to Fal")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        urls = list(pool.map(lambda path: _upload(path)[0], [prepared, sirio] + ([tein] if tein else [])))
    resolution = setting("FAL_DRAFT_RESOLUTION", "720p")
    model = _model_for(resolution)
    mode, fal_input = _reference_input(prepared, sirio, tein, prompt, urls, resolution)
    if is_mesh(folder):
        mesh_mode = json.loads((folder / "workflow-mode.json").read_text()).get("mode")
        description = "depth composite with face mesh overlay" if mesh_mode == "depth_mesh" else "original video with face mesh overlay"
        fal_input["prompt"] = fal_input["prompt"].replace("colored-depth composite", description) + " Remove all face mesh lines and any depth colors from the output; use them only for expression and lip motion guidance. Replace the entire original identity including hair. Preserve the exact embedded dialogue and timing."
    request = {"provider": "fal", "model": model, "resolution": resolution, "mode": mode, "input": fal_input, "asset_urls": urls}
    (folder / "seedance-request.json").write_text(json.dumps(request, indent=2))
    queued = _bridge("submit", {"model": model, "input": fal_input})
    ident = _request_id(queued)
    if not ident:
        raise ValueError("Fal did not return a request ID.")
    (folder / "seedance-response.json").write_text(json.dumps({"request_id": ident, "model": model, "provider": "fal"}, indent=2))
    (folder / "generation.json").write_text(json.dumps({"request_id": ident, "prompt": fal_input["prompt"], "video": "seedance-result.mp4", "mode": mode, "provider": "fal", "model": model}, indent=2))
    status("Fal Seedance draft submitted: " + ident)
    return ident


def _saved_request(folder):
    folder = Path(folder)
    request_file = folder / ("request.json" if folder.name == "hd" else "seedance-request.json")
    response_file = folder / ("response.json" if folder.name == "hd" else "seedance-response.json")
    request = json.loads(request_file.read_text())
    response = json.loads(response_file.read_text())
    return request, _request_id(response)


def wait_and_finish(folder, request_id=None, status=print):
    folder = Path(folder)
    request, saved_id = _saved_request(folder)
    request_id = request_id or saved_id
    if request_id != saved_id:
        raise ValueError("Saved Fal request ID does not match the requested collection ID.")
    for _ in range(360):
        current = _bridge("status", {"model": request["model"], "request_id": request_id})
        (folder / "provider-status.json").write_text(json.dumps(current, indent=2))
        state = str(current.get("status", "")).upper()
        if state in {"COMPLETED", "SUCCEEDED"}:
            result = _bridge("result", {"model": request["model"], "request_id": request_id})
            data = result.get("data", result)
            url = data.get("video", {}).get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError("Fal completed without a video URL.")
            downloaded = requests.get(url, timeout=180)
            downloaded.raise_for_status()
            (folder / "seedance-result.mp4").write_bytes(downloaded.content)
            status("Restoring entire original source audio · discarding generated audio")
            source_folder = folder if folder.name != "hd" else folder.parent
            finish_preview(folder / "seedance-result.mp4", source_folder, folder / "final-preview.mp4")
            return
        if state in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
            raise RuntimeError("Fal Seedance failed: " + str(current.get("error") or state))
        status("Fal Seedance status: " + (state or "QUEUED"))
        time.sleep(10)
    raise TimeoutError("Fal Seedance is still pending. Request ID is saved; do not resubmit automatically.")


def submit_hd(folder):
    """Submit approved inputs at 1080p; Fal has no draft-completion endpoint."""
    folder = Path(folder)
    hd = folder / "hd"
    if (hd / "response.json").exists():
        raise ValueError("1080p already submitted. Resume its saved request.")
    if not (folder / "final-preview.mp4").exists():
        raise ValueError("Complete and review a draft first.")
    original = json.loads((folder / "seedance-request.json").read_text())
    hd.mkdir(exist_ok=True)
    resolution = setting("FAL_HD_RESOLUTION", "1080p")
    fal_input = dict(original["input"])
    fal_input["resolution"] = resolution
    request = {"provider": "fal", "model": _model_for(resolution, hd=True), "resolution": resolution, "mode": original["mode"], "input": fal_input, "asset_urls": original["asset_urls"]}
    (hd / "request.json").write_text(json.dumps(request, indent=2))
    queued = _bridge("submit", {"model": request["model"], "input": fal_input})
    ident = _request_id(queued)
    if not ident:
        raise ValueError("Fal did not return an 1080p request ID.")
    (hd / "response.json").write_text(json.dumps({"request_id": ident, "model": request["model"], "provider": "fal"}, indent=2))
    return ident
