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


def _auto_sleep(what, exc, attempt, tries=3, base=3.0):
    """Sleep on transient timeout/network errors, then retry."""
    msg = str(exc)
    transient = any(k in msg for k in (
        "Timeout", "timed out", "Connection", "reset", "Read timed", "502", "503", "504"))
    if not transient or attempt >= tries:
        return False
    import random as _r
    nap = base * attempt + _r.uniform(0.3, 1.5)
    print("[img] %s timeout, auto-sleep %.1fs then retry %d/%d "
          "(%s)" % (what, nap, attempt + 1, tries, msg[:70]))
    time.sleep(nap)
    return True


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
    """Primary provider: furry gateway /images/generations (agnes-image-*).

    Auto-sleep + 2 passes on timeout so a slow gateway never kills the cycle."""
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
            key = credentials_refs(
                models.get("credential_file") or ".credentials.yaml"
            ).get(env_name, "")
    if not key:
        raise ImageError("no image gateway key (FURRY_API_KEY)")

    cand = []
    if os.getenv("MK49_IMG_MODEL"):
        cand.append(os.getenv("MK49_IMG_MODEL"))
    cand += list(models.get("image_models") or [])
    cand += ["agnes-image-2.5-flash", "agnes-image-2.1-flash"]
    size = size or models.get("image_size") or "1024x1024"
    endpoint = (models.get("image_endpoint") or "/images/generations")
    order = [m for m in dict.fromkeys([m for m in cand if m])]

    last_err = None
    for pass_no in range(2):          # 2nd pass only after auto-sleep
        for model in order:
            try:
                resp = _session().post(
                    base + endpoint,
                    headers={"Authorization": "Bearer " + key,
                             "Content-Type": "application/json"},
                    json={"model": model, "prompt": prompt, "n": 1,
                          "size": size},
                    timeout=timeout)
            except requests.RequestException as exc:
                last_err = "%s net %s" % (model, exc)
                if _auto_sleep("generate " + model, exc, pass_no, 2):
                    continue
                continue
            if resp.status_code != 200:
                last_err = "%s HTTP %s %s" % (model, resp.status_code,
                                              resp.text[:120])
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
                dl_ok = False
                for dl_try in range(3):
                    try:
                        img = _session().get(
                            item["url"], timeout=timeout,
                            headers={"User-Agent": "Mozilla/5.0"})
                        if img.status_code == 200 and img.content:
                            return img.content, _ext_for(
                                img.headers.get("content-type", ""),
                                img.content)
                        last_err = "%s download HTTP %s" % (
                            model, img.status_code)
                    except requests.RequestException as exc:
                        last_err = "%s download net %s" % (model, exc)
                        if not _auto_sleep("download " + model, exc,
                                           dl_try, 3):
                            break
                        continue
                    dl_ok = _auto_sleep("download " + model,
                                        Exception(last_err), dl_try, 3)
                    if not dl_ok:
                        break
                continue
            last_err = "%s empty payload" % model
        if last_err and ("net" in last_err or "download net" in last_err):
            time.sleep(4)
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


def upload_to_forum(client, raw_bytes, file_name=None, mime=None, tries=3):
    """Upload to forum storage (auto-sleep retry on timeout)."""
    if file_name is None:
        file_name = "agent_%d.png" % int(time.time())
    if mime is None:
        mime = "image/" + ("png" if file_name.endswith(".png") else "jpeg")
    data = None
    last = None
    for attempt in range(tries):
        try:
            data = client.upload_resource(raw_bytes, file_name, mime)
            break
        except Exception as exc:
            last = exc
            if _auto_sleep("upload " + file_name[:30], exc, attempt, tries):
                continue
            raise
    if data is None:
        raise ImageError("upload failed: %s" % str(last)[:140])
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


def fetch_remote(url, timeout=60, tries=3):
    last = None
    for attempt in range(tries):
        try:
            resp = _session().get(url, timeout=timeout,
                                  headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                last = ImageError("fetch HTTP %s" % resp.status_code)
                if _auto_sleep("fetch", last, attempt, tries):
                    continue
                raise last
            return resp.content, _ext_for(
                resp.headers.get("content-type", ""), resp.content)
        except Exception as exc:
            last = exc
            if _auto_sleep("fetch " + url.rsplit("/", 1)[-1][:40],
                           exc, attempt, tries):
                continue
            if isinstance(exc, ImageError):
                raise
            raise ImageError("fetch %s: %s" % (url, str(exc)[:120]))
    raise ImageError("fetch failed: %s" % str(last)[:140])


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
