"""Confirm the 3 sent messages live in the lobby + retry screenshot."""
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
LAST_ID = "6af9c33452e74eb6e9c0a3bd"   # last sent message id


def jshow(label, obj, limit=900):
    print("[%s] %s" % (label, json.dumps(obj, ensure_ascii=False)[:limit]))


def walk(o, out):
    """Collect every dict that looks like a chat message."""
    if isinstance(o, dict):
        if "converseId" in o and "author" in o:
            out.append(o)
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)


def main():
    S = requests.Session()
    S.trust_env = False
    S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    S.headers["Origin"] = BASE
    S.headers["Referer"] = BASE + "/"

    for a in range(3):
        try:
            r = S.post(BASE + "/api/user/login", json={
                "email": EMAIL, "password": PASSWORD}, timeout=40)
            break
        except Exception as e:
            print("login retry", a, str(e)[:80])
            time.sleep(3)
    d = r.json()
    tok = d["data"]["token"]
    uid = d["data"]["_id"]
    print("login ok, nick:", d["data"].get("nickname"))

    H = {"X-Token": tok}

    # --- fetchNearbyMessage around the last sent id ---
    got = []
    for path in (
        "/api/chat/message/fetchNearbyMessage?converseId=%s&messageId=%s&limit=10"
        % (LOBBY, LAST_ID),
        "/api/chat/message/fetchConverseMessage?converseId=%s&startId=%s&limit=30"
        % (LOBBY, LAST_ID),
        "/api/chat/message/fetchConverseMessage?converseId=%s" % LOBBY,
    ):
        try:
            r = S.get(BASE + path, headers=H, timeout=40)
            data = r.json()
        except Exception as e:
            print("GET ERR", path[:60], str(e)[:80])
            continue
        msgs = []
        walk(data, msgs)
        mine = [m for m in msgs if m.get("author") == uid]
        print("GET %-64s -> total=%d mine=%d"
              % (path.split("?")[0].replace("/api/chat/message/", ""),
                 len(msgs), len(mine)))
        got.extend(mine)
        if mine:
            jshow("sample mine", mine[-1])
            break

    # --- fetchConverseLastMessages POST (what the UI itself polls) ---
    try:
        r = S.post(BASE + "/api/chat/message/fetchConverseLastMessages",
                   headers=H, json={"converseIds": [LOBBY]}, timeout=40)
        data = r.json()
        msgs = []
        walk(data, msgs)
        mine = [m for m in msgs if m.get("author") == uid]
        print("POST fetchConverseLastMessages -> total=%d mine=%d"
              % (len(msgs), len(mine)))
        got.extend(mine)
        if msgs:
            jshow("tail structure", msgs[-1] if isinstance(msgs[-1], dict)
                  else data)
    except Exception as e:
        print("POST ERR", str(e)[:100])

    uniq = {}
    for m in got:
        uniq[m.get("_id")] = m
    print("\n=== my messages confirmed in lobby: %d ===" % len(uniq))
    for mid, m in uniq.items():
        c = m.get("content")
        print(" [%s] %s" % (str(mid)[-6:],
                            c if isinstance(c, str)
                            else json.dumps(c, ensure_ascii=False)[:80]))

    # --- screenshot with retries + settle ---
    out = pathlib.Path("state/probe")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled"])
            ctx = br.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0.0.0 Safari/537.36"))
            page = ctx.new_page()
            ok = False
            for attempt in range(3):
                try:
                    page.goto("%s/entry/login/?email=%s&password=%s"
                              % (BASE, EMAIL, PASSWORD),
                              timeout=50000, wait_until="domcontentloaded")
                    ok = True
                    break
                except Exception as e:
                    print("goto retry", attempt, str(e)[:70])
                    time.sleep(6)
            if ok:
                page.wait_for_timeout(4000)
                try:
                    b = page.locator("button:has-text('登录')").first
                    if b.is_visible(timeout=4000):
                        b.click()
                        page.wait_for_timeout(5500)
                except Exception:
                    pass
                for label in ("跳过引导", "跳过", "下一步"):
                    try:
                        b = page.locator("button:has-text('%s')" % label).first
                        if b.is_visible(timeout=1200):
                            b.click()
                            page.wait_for_timeout(900)
                            break
                    except Exception:
                        pass
                try:
                    b = page.locator("text=龙之归宿").first
                    if b.is_visible(timeout=5000):
                        b.click()
                        page.wait_for_timeout(5000)
                except Exception as e:
                    print("lobby nav:", str(e)[:70])
                page.screenshot(path=str(out / "chat_after.png"))
                try:
                    page.mouse.move(760, 520)
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(out / "chat_after2.png"))
                    t = " ".join(page.inner_text("body").split())
                    print("page text tail:", t[-420:])
                except Exception:
                    pass
                print("screenshot saved")
            br.close()
    except Exception as e:
        print("shot ERR", str(e)[:140])

    return 0


if __name__ == "__main__":
    sys.exit(main())
