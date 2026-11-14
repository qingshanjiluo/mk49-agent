"""Image toolkit: generate, store, list, reuse."""
import os
import time

from .base import Tool, schema, jdump

IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "state", "images")


class ImageGenerate(Tool):
    name = "image_generate"
    description = ("Generate an image from a Chinese or English prompt "
                   "(furry gateway agnes-image, pollinations fallback). "
                   "Saves locally under state/images and optionally uploads "
                   "to the forum for inline use. Returns path + forum URL.")
    params = schema({"prompt": ("string", "image prompt (vivid, concrete)"),
                     "upload": ("boolean", "upload to forum storage, "
                                          "default true")},
                    required=["prompt"])
    danger = True   # upload writes to forum storage

    def run(self, agent, prompt="", upload=True):
        from mk49 import images as img
        os.makedirs(IMG_DIR, exist_ok=True)
        raw, ext = img.generate(prompt, timeout=150)
        raw, ext = img.fit_for_forum(raw)
        stamp = int(time.time())
        local = os.path.join(IMG_DIR, "img_%s.%s" % (stamp, ext))
        with open(local, "wb") as fh:
            fh.write(raw)
        agent.state.stat_bump("images")
        result = {"local": os.path.relpath(local, os.path.dirname(IMG_DIR)),
                  "bytes": len(raw), "prompt": prompt[:80]}
        if upload:
            try:
                url = img.upload_to_forum(agent.client, raw,
                                          "agent_%s.%s" % (stamp, ext))
                result["forum_url"] = url
                result["markdown"] = "![img](%s)" % url
            except Exception as exc:
                result["upload_error"] = str(exc)[:120]
        return jdump(result)


class ImageList(Tool):
    name = "image_list"
    description = "List locally stored generated images."
    params = schema({}, required=[])

    def run(self, agent):
        if not os.path.isdir(IMG_DIR):
            return "no images yet"
        rows = []
        for fn in sorted(os.listdir(IMG_DIR))[-20:]:
            p = os.path.join(IMG_DIR, fn)
            rows.append({"file": fn, "kb": os.path.getsize(p) // 1024})
        return jdump(rows)


class ImageRead(Tool):
    name = "image_read"
    description = ("Get an image's markdown/forum URL for reuse inside a "
                   "post. Reads from local cache; uploads if not online yet.")
    params = schema({"filename": ("string", "file name from image_list")},
                    required=["filename"])

    def run(self, agent, filename=""):
        import re
        fn = re.sub(r"[^\w.\-]", "", filename)
        p = os.path.join(IMG_DIR, fn)
        if not os.path.isfile(p):
            return "ERROR: not found"
        with open(p, "rb") as fh:
            raw = fh.read()
        from mk49 import images as img
        url = img.upload_to_forum(agent.client, raw, fn)
        return jdump({"markdown": "![img](%s)" % url, "url": url})


def register_all(reg):
    for t in (ImageGenerate(), ImageList(), ImageRead()):
        reg.register(t)
