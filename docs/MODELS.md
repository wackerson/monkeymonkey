# Models and runtime

All hosted inference is performed through Fal with a single server-side `FAL_KEY`. The browser never receives that key.

| Stage | Fal model | Configuration |
|---|---|---|
| Vocal separation | [`fal-ai/demucs`](https://fal.ai/models/fal-ai/demucs/api) | `htdemucs`, WAV stems |
| Coloured temporal depth | [`fal-ai/depth-anything-video`](https://fal.ai/models/fal-ai/depth-anything-video/api) | VDA-Large, Turbo colormap, 24 fps |
| Subject masking | [`fal-ai/sam-3/video`](https://fal.ai/models/fal-ai/sam-3/video/api) | text prompt, mask-applied video converted to binary PNG frames for review/compositing |
| Draft generation | Fal Seedance 2.0 Fast Reference-to-Video | 720p default |
| Approved final generation | Fal Seedance 2.0 Reference-to-Video | new billed 1080p request |
| Pitch shifting | Rubber Band CLI | +3 semitones, time ratio 1 |
| Video/audio I/O | PyAV / FFmpeg libraries | normalization, compositing, AAC input vocals, source-audio remux |

Fal model access, usage limits, pricing, and output contracts are account-dependent. The workflow persists Fal request IDs and never automatically resubmits a timed-out paid request.
