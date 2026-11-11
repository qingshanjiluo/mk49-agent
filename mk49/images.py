"""Image generation + upload helpers.

Providers:
- pollinations : free, no key (https://image.pollinations.ai)
- local        : MK49_IMG_BASE_URL + MK49_IMG_API_KEY (OpenAI-compatible
                 /images/generations)
Any bytes are uploaded through the forum's own resource endpoint so the
resulting URL is first-party and hotlinkable inside posts.
"""

import io
import os
import time

import requests

RESOURCE_BASE = "/resources/"


class ImageError(Exception):
    pass


def _session():
    s = requests.Session()
    s.trust_env = False
    return s


def generate_pollinations(prompt, width=768, height=512, seed=None,
                           model="flux", timeout=90, retries=3):
    import random as _random
    last_err = None
    for attempt in range(retries):
        use_seed = seed if seed is not None else _random.randint(1, 999999)
        url = "https://image.pollinations.ai/prompt/%s" % requests.utils.quote(prompt)
        params = {"width": width, "height": height, "seed": use_seed,
                  "nologo": "true", "model": model}
        try:
            resp = _session().get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_err = "pollinations %s" % exc
            time.sleep(2)
            continue
        if resp.status_code == 402 or resp.status_code == 429:
            # free-tier quota hiccup: back off then retry
            last_err = "pollinations HTTP %d" % resp.status_code
            time.sleep(3)
            continue
        if resp.status_code != 200 or not resp.content:
            last_err = "pollinations HTTP %s" % resp.status_code
            time.sleep(1)
            continue
        ctype = resp.headers.get("content-type", "")
        if "image" not in ctype and len(resp.content) < 2048:
            last_err = "pollinations non-image: %s" % ctype
            continue
        return resp.content, _ext_for(ctype, resp.content)
    raise ImageError(last_err or "pollinations failed")


def generate_openai_style(prompt, width=768, height=512, timeout=120):
    base = os.getenv("MK49_IMG_BASE_URL")
    key = os.getenv("MK49_IMG_API_KEY")
    if not base or not key:
        raise ImageError("MK49_IMG_BASE_URL / MK49_IMG_API_KEY not set")
    payload = {
        "model": os.getenv("MK49_IMG_MODEL", "dall-e-3"),
        "prompt": prompt,
        "n": 1,
        "size": "%dx%d" % (width, height),
        "response_format": "b64_json",
    }
    resp = _session().post(
        base.rstrip("/") + "/images/generations",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"},
        json=payload, timeout=timeout,
    )
    if resp.status_code != 200:
        raise ImageError("image API HTTP %s: %s" % (resp.status_code, resp.text[:200]))
    data = resp.json()["data"][0]
    if data.get("b64_json"):
        import base64
        return base64.b64decode(data["b64_json"]), "png"
    if data.get("url"):
        img = _session().get(data["url"], timeout=timeout)
        img.raise_for_status()
        return img.content, _ext_for(img.headers.get("content-type", ""), img.content)
    raise ImageError("image API returned neither b64_json nor url")


def _ext_for(content_type, raw=b""):
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct or raw[:2] == b"\xff\xd8":
        return "jpg"
    if "webp" in ct or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"):
        return "webp"
    if "gif" in ct or raw[:3] == b"GIF":
        return "gif"
    return "png"



def _load_models(here):
    import json as _json
    try:
        with io.open(os.path.join(here, "models.json"), "r", encoding="utf-8") as fh:
            return _json.load(fh)
    except (OSError, ValueError):
        return {}


def generate_furry(prompt, size=None, timeout=180):
    """Primary provider: furry gateway /images/generations (agnes-image-*)."""
    import base64

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models = _load_models(here)
    base = (os.getenv("MK49_IMG_BASE_URL") or models.get("gateway")
            or "https://ai.furry.vg/v1").rstrip("/")
    key = os.getenv("MK49_IMG_API_KEY") or ""
    if not key:
        env_name = models.get("gateway_key_env") or "FURRY_API_KEY"
        key = os.getenv(env_name) or ""
        if not key:
            from .llm import credentials_refs
            key = credentials_refs(models.get("credential_file") or ".credentials.yaml").get(env_name, "")
    if not key:
        raise ImageError("no image gateway key (FURRY_API_KEY)")

    cand = []
    if os.getenv("MK49_IMG_MODEL"):
        cand.append(os.getenv("MK49_IMG_MODEL"))
    cand += list(models.get("image_models") or [])
    cand += ["agnes-image-2.5-flash", "agnes-image-2.1-flash"]
    size = size or models.get("image_size") or "1024x1024"
    endpoint = (models.get("image_endpoint") or "/images/generations")

    last_err = None
    for model in dict.fromkeys([m for m in cand if m]):
        try:
            resp = _session().post(
                base + endpoint,
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"},
                json={"model": model, "prompt": prompt, "n": 1, "size": size},
                timeout=timeout)

        except requests.RequestException as exc:
            last_err = "%s net %s" % (model, exc)
            continue
        if resp.status_code != 200:
            last_err = "%s HTTP %s %s" % (model, resp.status_code, resp.text[:120])
            continue
        try:
            data = resp.json()
            item = (data.get("data") or [{}])[0]
        except ValueError:
            last_err = "%s bad json" % model
            continue
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"]), "png"
        if item.get("url"):
            img = _session().get(item["url"], timeout=timeout,
                                 headers={"User-Agent": "Mozilla/5.0"})
            if img.status_code == 200 and img.content:
                return img.content, _ext_for(img.headers.get("content-type", ""), img.content)
            last_err = "%s download HTTP %s" % (model, img.status_code)
        else:
            last_err = "%s empty payload" % model
    raise ImageError(last_err or "furry image failed")


def generate(prompt, provider=None, **kw):
    provider = provider or os.getenv("MK49_IMG_PROVIDER", "furry")
    if provider in ("furry", "agnes"):
        return generate_furry(prompt, **kw)
    if provider == "pollinations":
        return generate_pollinations(prompt, **kw)
    if provider in ("local", "openai"):
        return generate_openai_style(prompt, **kw)
    raise ImageError("unknown image provider: %s" % provider)


def to_png_bytes(raw, max_width=None):
    """Normalize arbitrary bytes into PNG (optionally downscaled)."""
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    if max_width and im.width > max_width:
        ratio = max_width / float(im.width)
        im = im.resize((max_width, max(1, int(im.height * ratio))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def upload_to_forum(client, raw_bytes, file_name=None, mime=None):
    """Upload to forum storage, returns absolute URL for inline <img>/markdown."""
    if file_name is None:
        file_name = "agent_%d.png" % int(time.time())
    if mime is None:
        mime = "image/" + ("png" if file_name.endswith(".png") else "jpeg")
    data = client.upload_resource(raw_bytes, file_name, mime)
    path = data.get("filePath") or data.get("path") or data.get("url")
    if not path:
        raise ImageError("upload returned no filePath: %s" % data)
    if hasattr(client, "abs_resource_url"):
        return client.abs_resource_url(path)
    return client.base_url.rstrip("/") + RESOURCE_BASE + str(path).lstrip("/")


def generate_and_upload(client, prompt, provider=None, **kw):
    raw, ext = generate(prompt, provider=provider, **kw)
    url = upload_to_forum(client, raw, "agent_%d.%s" % (int(time.time()), ext))
    return url


def fetch_remote(url, timeout=60):
    resp = _session().get(url, timeout=timeout,
                          headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        raise ImageError("fetch %s -> HTTP %s" % (url, resp.status_code))
    return resp.content, _ext_for(resp.headers.get("content-type", ""), resp.content)


FORUM_MAX_UPLOAD = 1000 * 1000  # forum rejects uploads over 1MB


def fit_for_forum(raw, max_width=1280, quality=82):
    """Downscale/re-encode so the bytes fit the forum's 1MB upload limit."""
    if len(raw) <= FORUM_MAX_UPLOAD:
        return raw, "png"
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    if im.mode == "RGBA" or im.mode != "RGB":
        im = im.convert("RGB")
    for width, q in ((max_width, quality), (1024, 80), (896, 76), (768, 72)):
        ratio = width / float(im.width)
        out = im.resize((width, max(1, int(im.height * ratio))), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, format="JPEG", quality=q)
        data = buf.getvalue()
        if len(data) <= FORUM_MAX_UPLOAD:
            return data, "jpg"
    raise ImageError("cannot fit image under 1MB")
