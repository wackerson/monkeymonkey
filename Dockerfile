FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 HOST=0.0.0.0 DATA_DIR=/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends bash ffmpeg rubberband-cli ca-certificates && rm -rf /var/lib/apt/lists/*
# Copy the complete official Node runtime.  The Fal bridge invokes `node` at
# runtime, so copying only the launchers would omit libnode on some images.
COPY --from=node /usr/local /usr/local
COPY requirements.txt package.json ./
RUN pip install --no-cache-dir -r requirements.txt && npm install --omit=dev
COPY . .
# The UI exposes the optional face-mesh and depth+mesh modes, so include their
# isolated MediaPipe runtime in the deploy image as well.
RUN bash setup-face-mesh.sh
RUN mkdir -p /data
EXPOSE 8080
CMD ["python", "launch.py"]
