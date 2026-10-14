"""Start the private UI. Fal polling needs no public callback or tunnel."""
import os
import uvicorn

uvicorn.run("app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8770")))
