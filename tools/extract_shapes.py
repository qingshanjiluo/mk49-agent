"""Extract sendMessage/updateUserField call shapes + game client exports."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

s = io.open("state/probe/chat_app.js", encoding="utf-8", errors="replace").read()


def show(label, pat, before=100, after=320, limit=2):
    n = 0
    for m in re.finditer(pat, s):
        a = max(0, m.start() - before)
        print("=== %s ===" % label)
        print(s[a:m.end() + after].replace("\n", " ")[:520])
        print()
        n += 1
        if n >= limit:
            break
    if n == 0:
        print("=== %s : NOT FOUND ===" % label)


# sendMessage = fn(...) -> find the definition of `function fn(` or `fn=`
show("sendMessage def", r"function fn\(")
show("sendMessage assign", r"\bfn\s*=\s*")
# the actual POST to sendMessage endpoint
show("POST sendMessage", r'post\("/api/chat/message/sendMessage"')
# updateUserField call sites with literal fieldName
show("updateUserField literal", r'updateUserField".{0,200}')
show("modifyUserField call sites", r"\boo\([\"'][A-Za-z]+[\"']")
# settings shape
show("setUserSettings body", r'/api/user/setUserSettings".{0,260}')
# user settings keys
show("userSettings keys", r'getUserSettings.{0,300}')

# game client exports
g = io.open("state/probe/game_client.js", encoding="utf-8", errors="replace").read()
fns = sorted(set(re.findall(r"export function (\w+)", g)) |
             set(re.findall(r"__wbg_(\w+)", g)))
print("=== game client.js wasm-bindgen surface (n=%d) ===" % len(fns))
for f in fns[:70]:
    print(" ", f)

# game menu/route strings in client.js
routes = sorted(set(re.findall(r"/[a-z]+(?:/[a-z]+)*/?", g)))
print("\nclient routes:", [r for r in routes if any(
    k in r for k in ("profile", "rank", "room", "setting", "ship",
                     "team", "change", "login"))][:20])

# chat: find where modifyUserField/oo is invoked from UI (settings form)
for m in re.finditer(r"modifyUserField\(([^)]{0,80})\)", s):
    print("modifyUserField invoked:", m.group(1)[:120])
