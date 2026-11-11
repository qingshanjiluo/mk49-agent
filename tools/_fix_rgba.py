import io

P = "mk49/images.py"
s = io.open(P, encoding="utf-8").read()

old = '''    im = Image.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    for width, q in ((max_width, quality), (1024, 80), (896, 76), (768, 72)):'''
new = '''    im = Image.open(io.BytesIO(raw))
    if im.mode == "RGBA" or im.mode != "RGB":
        im = im.convert("RGB")
    for width, q in ((max_width, quality), (1024, 80), (896, 76), (768, 72)):'''
assert old in s, "anchor not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("RGBA->RGB fix applied")
