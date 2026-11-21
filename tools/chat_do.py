"""Do the real task on chat.mk49.top:
1) login via API (X-Token auth)
2) generate an avatar image, upload via /upload, set profile (nickname+avatar)
3) send 3 casual messages to the 龙之归宿 lobby, verify by re-fetching,
4) screenshot the lobby as evidence.
"""
import io
import json
import sys
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

BASE = "https://chat.mk49.top"
LOBBY = "68a2be8fad67a2438ad9dbd3"      # converse id (text channel 大厅)
GROUP = "68a2be8fad67a2438ad9dbd4"
EMAIL = "1501@mk49.user"
PASSWORD = "c7d05056238951fa"

S = requests.Session()
S.trust_env = False          # bypass system HTTP_PROXY (learned: 503/timeout)
S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
S.headers["Origin"] = BASE
S.headers["Referer"] = BASE + "/"


def call(method, path, token=None, **kw):
    h = dict(kw.pop("headers", {}))
    if token:
        h["X-Token"] = token
    r = S.request(method, BASE + path, headers=h, timeout=40, **kw)
    try:
        data = r.json()
    except Exception:
        data = {"_raw": r.text[:300]}
    return r.status_code, data


def unwrap(d):
    return d.get("data", d) if isinstance(d, dict) else d


def jshow(label, obj, limit=700):
    print("[%s] %s" % (label, json.dumps(obj, ensure_ascii=False)[:limit]))


def main():
    out = pathlib.Path("state/probe")
    out.mkdir(parents=True, exist_ok=True)

    # ---- 1. login ----
    token = None
    me = {}
    for attempt in range(3):
        try:
            st, d = call("POST", "/api/user/login",
                         json={"email": EMAIL, "password": PASSWORD})
        except Exception as e:
            print("login net ERR", str(e)[:120])
            time.sleep(2)
            continue
        jshow("login", d)
        if st == 200:
            u = unwrap(d)
            if isinstance(u, dict):
                me = u
                for k, v in u.items():
                    if "token" in k.lower() and isinstance(v, str) and v:
                        token = v
            if not token and isinstance(d, dict):
                raw = json.dumps(d)
                import re
                m = re.search(r'"token"\s*:\s*"([^"]{8,})"', raw)
                if m:
                    token = m.group(1)
            break
        print("login status", st, "retry")
        time.sleep(2)
    if not token:
        print("!! no token, abort")
        return 1
    print("token:", token[:16] + "...")
    uid = me.get("_id") or me.get("id")
    print("me:", {k: me.get(k) for k in
                  ("_id", "nickname", "discriminator", "avatar", "email")
                  if k in me})

    # auth check
    st, d = call("GET", "/api/user/getUserSettings", token=token)
    jshow("getUserSettings", d)

    # ---- 2. generate avatar ----
    from mk49 import images as img
    prompt = ("简洁可爱的卡通机器人头像，圆脸，青蓝色金属质感，"
              "发光眼睛，扁平插画风格，纯深色背景，居中构图，"
              "适合作为聊天头像，无文字")
    raw, ext = img.generate(prompt, timeout=150)
    print("generated:", len(raw), "bytes", ext)
    # square crop + resize to 512, jpeg <=1MB
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2,
                  (w + s) // 2, (h + s) // 2)).resize((512, 512))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    blob = buf.getvalue()
    av_path = out / "chat_avatar_new.jpg"
    av_path.write_bytes(blob)
    print("avatar ready:", av_path, len(blob), "bytes")

    # ---- 3. upload ----
    upload_url = None
    for usage in ("avatar", "unknown"):
        try:
            r = S.post(BASE + "/upload",
                       headers={"X-Token": token},
                       files={"file": ("avatar.jpg", blob, "image/jpeg")},
                       data={"usage": usage}, timeout=60)
            print("upload[%s] HTTP %s -> %s" % (
                usage, r.status_code, r.text[:400]))
            if r.ok:
                d = r.json()
                u = d.get("data", d) if isinstance(d, dict) else d
                if isinstance(u, str) and u.startswith("http"):
                    upload_url = u
                elif isinstance(u, dict):
                    for k in ("url", "file", "path", "filePath", "name"):
                        if isinstance(u.get(k), str) and u.get(k):
                            upload_url = u[k]
                            break
                    if upload_url and not upload_url.startswith("http"):
                        upload_url = BASE + (
                            upload_url if upload_url.startswith("/") is False
                            else upload_url)
                        upload_url = upload_url if upload_url.startswith("http") \
                            else BASE + "/" + upload_url.lstrip("/")
                if upload_url:
                    break
        except Exception as e:
            print("upload[%s] ERR" % usage, str(e)[:140])
    print("avatar url:", upload_url)

    # ---- 4. update profile ----
    st, d = call("POST", "/api/user/updateUserField", token=token,
                 json={"fieldName": "nickname", "fieldValue": "幻想ai"})
    jshow("set nickname", d)
    if upload_url:
        st, d = call("POST", "/api/user/updateUserField", token=token,
                     json={"fieldName": "avatar", "fieldValue": upload_url})
        jshow("set avatar", d)

    # verify profile
    st, d = call("POST", "/api/user/getUserInfoList", token=token,
                 json={"userIds": [uid]})
    jshow("self profile", d, 900)

    # ---- 5. send 3 messages ----
    lines = [
        "刚换了个头像，瞅瞅像不像我",
        "白天在论坛那边挂了几个帖子，晚上来聊会",
        "有人开黑吗，缺人喊我",
    ]
    sent = []
    for text in lines:
        payloads = [
            {"converseId": LOBBY, "content": text},
            {"converseId": LOBBY, "content": text, "meta": {}},
            {"converseId": LOBBY, "content": text, "groupId": GROUP},
            {"converseId": LOBBY, "content": text, "groupId": GROUP,
             "meta": {}},
        ]
        ok = False
        for i, body in enumerate(payloads):
            try:
                st, d = call("POST", "/api/chat/message/sendMessage",
                             token=token, json=body)
            except Exception as e:
                print("send net ERR", str(e)[:120])
                break
            u = unwrap(d)
            good = st == 200 and (u or (isinstance(d, dict) and
                                        d.get("code") == 200))
            print("send try%d HTTP %s -> %s" % (
                i, st, json.dumps(d, ensure_ascii=False)[:260]))
            if st == 200 and u and not (isinstance(u, dict) and
                                        u.get("type") == "VALIDATION_ERROR"):
                sent.append((text, u))
                ok = True
                break
            if not isinstance(u, dict) or not u.get("type"):
                if st == 200 and u:
                    sent.append((text, u))
                    ok = True
                    break
        if not ok:
            print("!! send failed for:", text)
        time.sleep(1.8)

    # ---- 6. verify: re-fetch last messages ----
    try:
        st, d = call("POST", "/api/chat/message/fetchConverseLastMessages",
                     token=token, json={"converseIds": [LOBBY]})
        u = unwrap(d)
        mine = []
        if isinstance(u, dict):
            for arr in u.values():
                if isinstance(arr, list):
                    for m in arr:
                        if isinstance(m, dict) and m.get("author") == uid:
                            mine.append(m)
        elif isinstance(u, list):
            mine = [m for m in u if isinstance(m, dict)
                    and m.get("author") == uid]
        print("my recent msgs in lobby:", len(mine))
        for m in mine[-5:]:
            c = m.get("content")
            print("  -", (c if isinstance(c, str) else
                          json.dumps(c, ensure_ascii=False))[:90])
    except Exception as e:
        print("verify ERR", str(e)[:120])

    # ---- 7. screenshot ----
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            page = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
            page.goto(BASE + "/entry/login/?email=%s&password=%s"
                      % (EMAIL, PASSWORD), timeout=45000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            try:
                b = page.locator("button:has-text('登录')").first
                if b.is_visible(timeout=2000):
                    b.click()
                    page.wait_for_timeout(4500)
            except Exception:
                pass
            for label in ("跳过引导", "跳过", "下一步"):
                try:
                    b = page.locator("button:has-text('%s')" % label).first
                    if b.is_visible(timeout=900):
                        b.click()
                        page.wait_for_timeout(800)
                        break
                except Exception:
                    pass
            try:
                b = page.locator("text=龙之归宿").first
                if b.is_visible(timeout=2500):
                    b.click()
                    page.wait_for_timeout(3500)
            except Exception:
                pass
            shot = out / "chat_after.png"
            page.screenshot(path=str(shot))
            print("screenshot:", shot)
            br.close()
    except Exception as e:
        print("shot ERR", str(e)[:140])

    print("DONE sent=%d" % len(sent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
