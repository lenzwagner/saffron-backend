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

# Option 1: Session cookie (recommended — works from any IP including datacenter)
_ig_session = os.environ.get("IG_SESSION_ID")
if _ig_session:
    try:
        import requests
        L.context._session.cookies.set("sessionid", _ig_session, domain=".instagram.com")
        L.context._session.cookies.set("ds_user_id", os.environ.get("IG_USER_ID", ""), domain=".instagram.com")
        print("Instagram session cookie loaded")
    except Exception as e:
        print(f"Session cookie setup failed: {e}")

# Option 2: Username/password fallback
elif os.environ.get("IG_USERNAME") and os.environ.get("IG_PASSWORD"):
    try:
        L.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])
        print(f"Logged in to Instagram as {os.environ['IG_USERNAME']}")
    except Exception as e:
        print(f"Instagram login failed: {e}")

# Simple in-memory cache: shortcode → (timestamp, result)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 hour


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/instagram/{shortcode}")
def get_instagram_post(shortcode: str, session_id: str = ""):
    # Use per-request session ID if provided (overrides the env-var one)
    effective_session = session_id.strip() or _ig_session or ""
    if effective_session:
        L.context._session.cookies.set("sessionid", effective_session, domain=".instagram.com")

    # Return cached result if still fresh (only when using the same session)
    cache_key = f"{shortcode}:{effective_session[:8] if effective_session else ''}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < CACHE_TTL:
        return cached[1]

    try:
        post = Post.from_shortcode(L.context, shortcode)
        result = {
            "caption": post.caption or "",
            "thumbnail_url": post.url or "",
        }
        _cache[cache_key] = (time.time(), result)
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
