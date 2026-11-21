"""Extract sendMessage payload shape, file-upload endpoint, profile edit fields
from chat_app.js bundle."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

s = io.open("state/probe/chat_app.js", encoding="utf-8", errors="replace").read()


def show(label, pat, before=140, after=380, limit=3, flags=0):
    n = 0
    for m in re.finditer(pat, s, flags):
        a = max(0, m.start() - before)
        print("=== %s #%d ===" % (label, n + 1))
        print(s[a:m.end() + after].replace("\n", " ")[:640])
        print()
        n += 1
        if n >= limit:
            break
    if n == 0:
        print("=== %s : NOT FOUND ===" % label)


# 1) sendMessage called with an object literal -> field names
show("sendMessage() call w/ obj", r"sendMessage\(\{[^}]{10,300}")
show("sendMessage(x) callers", r"(?<!function )\bfn\(\{[^}]{10,300}")

# 2) message payload fields around converseId+content patterns
show("converseId+content pair", r"converseId:\s*\w+,\s*content", before=100, after=260, limit=3)

# 3) file upload endpoint
show("upload endpoint", r'/api/[A-Za-z0-9:/_.\-]*upload[A-Za-z0-9:/_.\-]*', before=60, after=200, limit=4)
show("upload fn", r"uploadFile|uploadAvatar|file\.upload|/upload\b", before=80, after=240, limit=3)

# 4) profile edit UI: uniqueName/nickname/status fields
for kw in ("uniqueName", "nickname", "status", "signature", "introduction", "avatar"):
    show("field %s" % kw, re.escape(kw) + r"[:=]", before=80, after=160, limit=1)

# 5) updateProfile-like composite
show("updateProfile-ish", r"updateProfile|editProfile|saveProfile|submitProfile", before=100, after=300, limit=2)
