"""Shared Fal queue and file-storage adapter for preprocessing jobs."""
from pathlib import Path
import json
import os
import subprocess
import time

import requests

from config import ROOT, credential


def _bridge(action, payload):
    """Call the server-side Node Fal client without exposing FAL_KEY to the UI."""
    credential("FAL_KEY")
    result = subprocess.run(
        ["node", str(ROOT / "fal_bridge.mjs"), action],
        input=json.dumps(payload), text=True, capture_output=True, timeout=300,
        env=os.environ.copy(),
    )
    if result.returncode:
        raise RuntimeError("Fal " + action + " failed: " + (result.stderr.strip() or result.stdout.strip()))
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Fal returned an unreadable response.") from error


def upload(path):
    return _bridge("upload", {"paths": [str(path)]})["urls"][0]


def file_url(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("url"), str):
        return value["url"]
    raise ValueError("Fal completed without a downloadable file URL.")


def run(model, input_data, folder, artifact, status=print):
    """Submit, persist, poll, and return a Fal model result without resubmission."""
    folder = Path(folder)
    request_path = folder / f"fal-{artifact}-request.json"
    response_path = folder / f"fal-{artifact}-response.json"
    if request_path.exists() or response_path.exists():
        raise ValueError(f"Fal {artifact} already has a saved request; prepare a new job instead of resubmitting.")
    queued = _bridge("submit", {"model": model, "input": input_data})
    request_id = queued.get("request_id") or queued.get("requestId")
    if not request_id:
        raise RuntimeError("Fal did not return a request ID.")
    request_path.write_text(json.dumps({"model": model, "input": input_data, "request_id": request_id}, indent=2))
    for _ in range(360):
        current = _bridge("status", {"model": model, "request_id": request_id})
        state = str(current.get("status", "")).upper()
        if state in {"COMPLETED", "SUCCEEDED"}:
            result = _bridge("result", {"model": model, "request_id": request_id})
            response_path.write_text(json.dumps(result, indent=2))
            return result.get("data", result), request_id
        if state in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
            response_path.write_text(json.dumps(current, indent=2))
            raise RuntimeError("Fal " + artifact + " failed: " + str(current.get("error") or state))
        status("Fal " + artifact + " status: " + (state or "QUEUED"))
        time.sleep(5)
    raise TimeoutError(f"Fal {artifact} is still pending. Its request ID is saved; do not resubmit automatically.")


def download(url, target):
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    Path(target).write_bytes(response.content)
    return Path(target)
