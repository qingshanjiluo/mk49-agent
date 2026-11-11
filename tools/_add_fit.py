import io

P = "mk49/images.py"
s = io.open(P, encoding="utf-8").read()

if "FORUM_MAX_UPLOAD" in s:
    print("already patched")
    raise SystemExit(0)

addition = '''

FORUM_MAX_UPLOAD = 1000 * 1000  # forum rejects uploads over 1MB


def fit_for_forum(raw, max_width=1280, quality=82):
    """Downscale/re-encode so the bytes fit the forum's 1MB upload limit."""
    if len(raw) <= FORUM_MAX_UPLOAD:
        return raw, "png"
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "RGBA"):
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
'''
s = s.rstrip() + "\n" + addition
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("fit_for_forum added")
