"""Forum image vision toolkit: extract, download and describe images
found inside a thread or one comment (vision + text fallback)."""
import os
import time

from .base import Tool, schema, jdump

IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "state", "images", "forum")
RESOURCE_HINT = "/bbs/resources/"


def resolve_img_url(src, origin="https://forum.mk49.top"):
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("http"):
        return src
    if src.startswith("/bbs/") or src.startswith(RESOURCE_HINT):
        return origin + src if src.startswith("/bbs/") else origin + src
    if src.startswith("mk") or "/" in src:
        return origin + RESOURCE_HINT + src.lstrip("/")
    return ""


def extract_thread_images(html, limit=6):
    from mbbs.content import IMG_RE, IMG_MD_RE
    urls = IMG_RE.findall(html or "") + IMG_MD_RE.findall(html or "")
    out = []
    for u in urls:
        r = resolve_img_url(u)
        if r and r not in out:
            out.append(r)
        if len(out) >= limit:
            break
    return out


class ReadThreadImages(Tool):
    name = "forum_read_thread_images"
    description = ("Extract and describe images posted in a thread: downloads "
                  "up to 4 images, runs vision (smart model) to describe "
                  "what is actually shown. Use before commenting on "
                  "image-heavy posts.")
    params = schema({"thread_id": ("integer", "thread id"),
                     "max_images": ("integer", "max to describe, default 3"),
                     "save_notes": ("boolean",
                                    "store descriptions into mem notes")},
                    required=["thread_id"])
    max_result = 3500

    def run(self, agent, thread_id=0, max_images=3, save_notes=True):
        detail = agent.client.thread_detail(thread_id) or {}
        html = detail.get("content") or detail.get("content_for_indexes") or ""
        urls = extract_thread_images(html, limit=6)
        if not urls:
            return jdump({"thread": thread_id, "images": [],
                          "note": "no images in this thread"})
        os.makedirs(IMG_DIR, exist_ok=True)
        results = []
        from mk49 import images as imglib
        for i, u in enumerate(urls[: max(1, int(max_images or 3))]):
            raw = None
            try:
                # reuse cache when possible
                name = u.rsplit("/", 1)[-1].split("?")[0][:60]
                cache = os.path.join(IMG_DIR, name)
                if os.path.exists(cache) and os.path.getsize(cache) > 500:
                    with open(cache, "rb") as fh:
                        raw = fh.read()
                else:
                    raw, ext = imglib.fetch_remote(u, timeout=40)
                    with open(cache, "wb") as fh:
                        fh.write(raw)
            except Exception as exc:
                results.append({"url": u, "desc": "download failed: %s"
                               % str(exc)[:60]})
                continue
            desc = ""
            try:
                desc = agent.llm.describe_image_bytes(
                    raw, "Describe this forum post image briefly in Chinese: "
                         "what is shown, any text visible. Max 60 chars.")
            except Exception as exc:
                results.append({"url": u, "desc": "vision failed: %s"
                               % str(exc)[:60]})
                continue
            entry = {"url": u, "bytes": len(raw), "desc": (desc or "").strip()[:160]}
            results.append(entry)
            agent.state.log("vision", "thread=%s %s" % (thread_id,
                                                        entry["desc"][:60]))
            if save_notes and entry["desc"]:
                try:
                    agent.memory.state.data.setdefault("notes", [])
                    agent.memory.state.data["notes"].append({
                        "id": "img%d" % int(time.time() * 1000 % 1e8),
                        "ts": time.time(),
                        "text": "thread %s image: %s" % (thread_id, entry["desc"]),
                        "tags": ["image", "vision"],
                        "links": [],
                    })
                except Exception:
                    pass
        return jdump({"thread": thread_id, "images": results})


def register_all(reg):
    reg.register(ReadThreadImages())
