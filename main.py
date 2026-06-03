import os
import time
import threading
import urllib.request
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from instaloader import Instaloader, Post, exceptions as insta_exceptions
import uvicorn

app = FastAPI(title="Saffron Instagram API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

L = Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    quiet=True,
)

# Simple in-memory cache: shortcode → (timestamp, result)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 hour


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/instagram/{shortcode}")
def get_instagram_post(shortcode: str):
    # Return cached result if still fresh
    cached = _cache.get(shortcode)
    if cached and (time.time() - cached[0]) < CACHE_TTL:
        return cached[1]

    try:
        post = Post.from_shortcode(L.context, shortcode)
        result = {
            "caption": post.caption or "",
            "thumbnail_url": post.url or "",
        }
        _cache[shortcode] = (time.time(), result)
        return result
    except insta_exceptions.LoginRequiredException:
        raise HTTPException(status_code=403, detail="Post requires login (private or age-restricted)")
    except insta_exceptions.PostChangedException:
        raise HTTPException(status_code=404, detail="Post not found or deleted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _keep_alive():
    """Ping own /health every 10 min so Render's free tier doesn't sleep."""
    port = int(os.environ.get("PORT", 8000))
    url = f"http://localhost:{port}/health"
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(url, timeout=5)
        except Exception:
            pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    threading.Thread(target=_keep_alive, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=port)
