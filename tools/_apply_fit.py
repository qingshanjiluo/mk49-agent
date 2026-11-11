"""Apply the 1MB upload fit to image_post and command_center /image."""
import io

for P in ("features/image_post.py", "features/command_center.py"):
    s = io.open(P, encoding="utf-8").read()
    changed = False
    if "fit_for_forum" not in s:
        # insert after each "raw, ext = img.generate(...)" line
        out_lines = []
        for ln in s.split("\n"):
            out_lines.append(ln)
            stripped = ln.strip()
            if stripped.startswith("raw, ext = img.generate("):
                indent = ln[: len(ln) - len(ln.lstrip())]
                out_lines.append(indent + "raw, ext = img.fit_for_forum(raw)")
                changed = True
        s = "\n".join(out_lines)
    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print(P, "patched" if changed else "no generate call found")
