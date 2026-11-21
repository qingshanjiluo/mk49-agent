"""Game client.js/wasm string extraction: endpoints, ws protocol, name/chat."""
import io
import re
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url):
    with OPENER.open(url, timeout=60) as r:
        return r.read()


def dump(label, blob):
    text = blob.decode("utf-8", "ignore")
    pats = {
        "url": r"https?://[\w./\-?=&%]{4,80}",
        "ws": r"wss?://[\w./\-]{4,60}",
        "chat/name": r"[\w./\-]*(?:nick|nickname|playerName|player_name|displayName|sendChat|send_chat|chatMessage|chat_message|set_name|changeName)[\w./\-]*",
    }
    print("== %s (%d bytes) ==" % (label, len(blob)))
    for k, p in pats.items():
        hits = sorted(set(re.findall(p, text, re.I)))[:24]
        if hits:
            print(" [%s] %s" % (k, hits))


def wasm_strings(blob):
    # ascii runs >= 6 from wasm
    runs = re.findall(rb"[\x20-\x7e]{6,60}", blob)
    keys = (b"chat", b"nick", b"name", b"token", b"mk49", b"login",
            b"send", b"message", b"ws://", b"wss://", b"/api/", b"team")
    out = set()
    for r in runs:
        low = r.lower()
        if any(k in low for k in keys):
            out.add(r.decode("ascii", "ignore"))
    for s in sorted(out)[:40]:
        print("  wasm|", s)


def main():
    js = fetch("https://game.mk49.top/client.js")
    dump("client.js", js)
    # comments often reveal source file names / lib versions
    head = js[:3000].decode("utf-8", "ignore")
    print("--- client.js head ---")
    print(re.sub(r"\s+", " ", head[:700]))
    try:
        wasm = fetch("https://game.mk49.top/client_bg.wasm")
        print("== wasm %d bytes ==" % len(wasm))
        wasm_strings(wasm)
    except Exception as e:
        print("wasm ERR", e)
    # index tail: game scripts + game config
    idx = fetch("https://game.mk49.top/").decode("utf-8", "ignore")
    print("--- index scripts ---")
    for m in re.finditer(r"<script[^>]*src=\"([^\"]+)\"", idx):
        print("  script:", m.group(1))
    for m in re.finditer(r"(?:gameConfig|window\.\w+)\s*=\s*\{[^}]{0,200}", idx):
        print("  cfg:", m.group(0)[:200])
    # inline js in index (token handling)
    for m in re.finditer(r"<script>(.*?)</script>", idx, re.S):
        body = m.group(1).strip()
        if body:
            print("--- inline js (%d) ---" % len(body))
            print(body[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
