"""Final confirm: full lobby fetch (no pagination), profile, screenshot."""
import io
import json
import sys
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

BASE = "https://chat.mk49.top"
LOBBY = "68a2be8fad67a2438ad9dbd3"
EMAIL = "1501@mk49.user"
PASSWORD = "c7d05056238951fa"


def walk(o, out):
    if isinstance(o, dict):
        if "converseId" in o and "author" in o:
            out.append(o)
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)


def main():
    out = pathlib.Path("state/probe")
    S = requests.Session()
    S.trust_env = False
    S.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Origin": BASE, "Referer": BASE + "/"})
    d = S.post(BASE + "/api/user/login",
               json={"email": EMAIL, "password": PASSWORD},
               timeout=40).json()
    tok = d["data"]["token"]
    uid = d["data"]["_id"]
    H = {"X-Token": tok}
    print("login ok, nick:", d["data"].get("nickname"))

    msgs = []
    r = S.get(BASE + "/api/chat/message/fetchConverseMessage?converseId=" +
              LOBBY, headers=H, timeout=40).json()
    walk(r, msgs)
    mine = [m for m in msgs if m.get("author") == uid]
    print("total=%d mine=%d" % (len(msgs), len(mine)))
    for m in mine:
        print(" [%s] %s" % (m["_id"][-6:], m["content"]))

    r = S.post(BASE + "/api/user/getUserInfoList", headers=H,
               json={"userIds": [uid]}, timeout=40).json()
    me = r["data"][0]
    print("profile:", me["nickname"], "| disc:", me["discriminator"],
          "| avatar:", (me.get("avatar") or "")[:120])

    # screenshot (retries)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            p = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
            for a in range(3):
                try:
                    p.goto("%s/entry/login/?email=1501%%40mk49.user&password=%s"
                           % (BASE, PASSWORD), timeout=50000,
                           wait_until="domcontentloaded")
                    break
                except Exception as e:
                    print("goto retry", a, str(e)[:60])
                    time.sleep(8)
            p.wait_for_timeout(4000)
            try:
                b = p.locator("button:has-text('登录')").first
                if b.is_visible(timeout=4000):
                    b.click()
                    p.wait_for_timeout(5500)
            except Exception:
                pass
            for lab in ("跳过引导", "跳过", "下一步"):
                try:
                    b = p.locator("button:has-text('%s')" % lab).first
                    if b.is_visible(timeout=1000):
                        b.click()
                        p.wait_for_timeout(900)
                        break
                except Exception:
                    pass
            try:
                b = p.locator("text=龙之归宿").first
                if b.is_visible(timeout=5000):
                    b.click()
                    p.wait_for_timeout(5000)
            except Exception as e:
                print("nav", str(e)[:60])
            p.screenshot(path=str(out / "chat_after.png"))
            p.mouse.move(760, 520)
            p.mouse.wheel(0, 5000)
            p.wait_for_timeout(1500)
            p.screenshot(path=str(out / "chat_after2.png"))
            print("screenshot ok")
            br.close()
    except Exception as e:
        print("shot ERR", str(e)[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())
