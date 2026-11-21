"""Find: auth header name, sendMessage caller payload, upload response usage."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
s = io.open("state/probe/chat_app.js", encoding="utf-8", errors="replace").read()


def show(label, pat, before=160, after=420, limit=3):
    n = 0
    for m in re.finditer(pat, s):
        a = max(0, m.start() - before)
        print("=== %s #%d ===" % (label, n + 1))
        print(s[a:m.end() + after].replace("\n", " ")[:700])
        print()
        n += 1
        if n >= limit:
            break
    if n == 0:
        print("=== %s : NOT FOUND ===" % label)


# auth header
show("Authorization", r"Authorization")
show("token header", r"headers\.\w*[Tt]oken\w*\s*=|headers\[.{0,10}token", before=120, after=300, limit=3)
show("axios defaults token", r"defaults\.headers|interceptors\.request\.use", before=60, after=420, limit=2)
show("token storage", r"localStorage.{0,60}token|token.{0,50}localStorage", before=80, after=200, limit=2)

# login response usage
show("loginWithEmail", r'"/api/user/login".{0,500}', before=40, after=40, limit=2)

# sendMessage callers
show("caller .sendMessage(", r"\.sendMessage\(", before=200, after=260, limit=3)
show("caller sendMessage({", r"sendMessage\(\{", before=60, after=320, limit=3)

# message meta shape
show("meta type", r"meta:\s*\{.{0,120}", before=60, after=60, limit=4)
show("contentType/text kind", r'"text"\s*:\s*!0|kind:\s*"text"|type:\s*"text"', before=80, after=140, limit=2)

# upload response / usage values
show("usage value", r'append\("usage".{0,160}', before=40, after=40, limit=2)
show("upload resp url", r"fileUrl|fileURL|url.{0,30}data\.", before=80, after=160, limit=3)
