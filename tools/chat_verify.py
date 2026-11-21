"""Fix avatar {BACKEND} placeholder, re-verify profile + lobby messages,
retry screenshot."""
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
GROUP = "68a2be8fad67a2438ad9dbd4"
EMAIL = "1501@mk49.user"
PASSWORD = "c7d05056238951fa"

S = requests.Session()
S.trust_env = False
S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
S.headers["Origin"] = BASE
S.headers["Referer"] = BASE + "/"


def call(method, path, token=None, **kw):
    h = dict(kw.pop("headers", {}))
    if token:
        h["X-Token"] = token
    for a in range(3):
        try:
            r = S.request(method, BASE + path, headers=h, timeout=40, **kw)
            break
        except Exception as e:
            if a == 2:
                raise
            time.sleep(2)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


def jshow(label, obj, limit=600):
    print("[%s] %s" % (label, json.dumps(obj, ensure_ascii=False)[:limit]))


def main():
    out = pathlib.Path("state/probe")
    # login
    st, d = call("POST", "/api/user/login",
                 json={"email": EMAIL, "password": PASSWORD})
    tok = d.get("data", {}).get("token")
    uid = d.get("data", {}).get("_id")
    print("token ok:", bool(tok), "| uid:", uid)

    # fix avatar url placeholder
    st, d = call("POST", "/api/user/getUserInfoList", token=tok,
                 json={"userIds": [uid]})
    me = (d.get("data") or [{}])[0]
    avatar = me.get("avatar") or ""
    print("avatar now:", avatar[:140])
    if "{BACKEND}" in avatar:
        fixed = avatar.replace("{BACKEND}", "").replace(
            "chat.mk49.top/static", "chat.mk49.top/static")
        # collapse host+placeholder into proper static path
        fixed = avatar.replace("{BACKEND}", "")
        fixed = fixed.replace("chat.mk49.top/static", "chat.mk49.top/static")
        if "{BACKEND}" in fixed:
            fixed = fixed.replace("https://chat.mk49.top", "")
            fixed = fixed.replace("{BACKEND}", "")
            fixed = BASE + (fixed if fixed.startswith("/static") is False
                            else fixed)
        # final normalize: host + "/static/..."
        idx = fixed.find("/static/")
        fixed = BASE + fixed[idx:] if idx >= 0 else fixed
        print("fixed:", fixed)
        st, d = call("POST", "/api/user/updateUserField", token=tok,
                     json={"fieldName": "avatar", "fieldValue": fixed})
        jshow("set avatar fixed", d)

    # verify profile
    st, d = call("POST", "/api/user/getUserInfoList", token=tok,
                 json={"userIds": [uid]})
    me = (d.get("data") or [{}])[0]
    print("profile:", me.get("nickname"), "| avatar:",
          (me.get("avatar") or "")[:120])

    # verify avatar URL serves an image
    av = me.get("avatar") or ""
    if av.startswith("http"):
        try:
            r = S.get(av, timeout=30)
            print("avatar GET:", r.status_code, r.headers.get("content-type"),
                  len(r.content), "bytes")
        except Exception as e:
            print("avatar GET ERR", str(e)[:100])

    # verify messages via GET converse
    try:
        st, d = call("GET", "/api/chat/message/fetchConverseMessage?converseId=%s"
                     % LOBBY, token=tok)
        u = d.get("data") or d
        msgs = []
        if isinstance(u, dict):
            msgs = u.get("messages") or u.get("list") or []
            if not msgs:
                for v in u.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        msgs = v
                        break
        elif isinstance(u, list):
            msgs = u
        mine = [m for m in msgs if m.get("author") == uid]
        print("fetched msgs:", len(msgs), "| mine:", len(mine))
        for m in mine[-5:]:
            c = m.get("content")
            print("  [%s] %s" % (
                m.get("_id", "")[-6:],
                c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)))
    except Exception as e:
        print("fetch ERR", str(e)[:120])

    # screenshot with retries
    shot = out / "chat_after.png"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            page = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
            page.goto("%s/entry/login/?email=%s&password=%s"
                      % (BASE, EMAIL, PASSWORD), timeout=60000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(3500)
            try:
                b = page.locator("button:has-text('登录')").first
                if b.is_visible(timeout=3000):
                    b.click()
                    page.wait_for_timeout(5000)
            except Exception:
                pass
            for label in ("跳过引导", "跳过", "下一步"):
                try:
                    b = page.locator("button:has-text('%s')" % label).first
                    if b.is_visible(timeout=1000):
                        b.click()
                        page.wait_for_timeout(900)
                        break
                except Exception:
                    pass
            try:
                b = page.locator("text=龙之归宿").first
                if b.is_visible(timeout=4000):
                    b.click()
                    page.wait_for_timeout(4500)
            except Exception as e:
                print("lobby nav:", str(e)[:80])
            page.screenshot(path=str(shot))
            # scroll message list to bottom
            try:
                page.mouse.move(720, 500)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1200)
                page.screenshot(path=str(out / "chat_after2.png"))
            except Exception:
                pass
            print("screenshot:", shot)
            br.close()
    except Exception as e:
        print("shot ERR", str(e)[:140])

    # header avatar preview link
    print("avatar file:", out / "chat_avatar_new.jpg",
          (out / "chat_avatar_new.jpg").stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
