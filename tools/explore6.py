"""Final combined probe:
- game: block devtool-blocked redirect, dump menu pages /settings/ /profile/
  /rooms/ /team/ /rankings/
- chat: fixed fill() send-capture with marker abort, settings menu via proper
  sidebar avatar, getUserSettings with captured request headers
"""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent

MARK = "send-probe-keep"


def snap(page, tag, out):
    try:
        page.wait_for_timeout(3500)
        print("--- %s ---" % tag)
        print("url:", page.url[:120])
        try:
            print("title:", page.title()[:60])
        except Exception:
            pass
        try:
            t = " ".join(page.inner_text("body").split())[:500]
            print("text:", t)
        except Exception:
            pass
        try:
            ins = page.eval_on_selector_all(
                "input, textarea",
                "els => els.slice(0,12).map(e => [e.type||'', e.name||e.id||'', "
                "e.placeholder||'', (e.value||'').slice(0,30)])")
            print("inputs:", ins)
        except Exception:
            pass
        try:
            page.screenshot(path=str(out / (tag + ".png")))
        except Exception:
            pass
    except Exception as e:
        print(tag, "ERR", str(e)[:120])


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    token = agent.client.token
    out = pathlib.Path("state/probe")
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # ============ GAME pages (block anti-devtools redirect) ============
        print("### GAME menu pages ###")

        def block_devtools(r):
            if "devtool-blocked" in r.request.url:
                r.abort()
                return
            r.continue_()
        ctx.route("**/*", block_devtools)

        sent_headers = {}
        got_send = []
        try:
            page.goto("https://game.mk49.top/?mk49Token=" + token,
                      timeout=45000, wait_until="commit")
            page.wait_for_timeout(8000)
            for route in ("/settings/", "/profile/", "/rooms/", "/team/",
                          "/rankings/", "/ships/"):
                try:
                    page.evaluate(
                        "r => location.hash = '' && history.pushState({},'',r)",
                        route)
                    page.reload(timeout=30000, wait_until="commit")
                    page.wait_for_timeout(5000)
                    snap(page, "game" + route.strip("/").replace("/", "_"),
                         out)
                except Exception as e:
                    print("route", route, "ERR", str(e)[:110])
        except Exception as exc:
            print("game ERR", str(exc)[:140])

        # ============ CHAT send capture + settings ============
        print("\n### CHAT send/settings ###")
        ctx.unroute("**/*")

        def cap(r):
            if r.request.method == "POST" and "/api/" in r.request.url:
                body = r.request.post_data or ""
                if MARK in body:
                    got_send.append((r.request.url.replace(
                        "https://chat.mk49.top", ""), body[:300]))
                    r.fulfill(status=200, body='{"data":"ok"}',
                              content_type="application/json")
                    return
            r.continue_()
        ctx.route("**/api/**", cap)

        def hdr(r):
            if "getUserSettings" in r.url:
                sent_headers.update(r.headers)
        page.on("request", hdr)

        ca = agent.client.get("chatAccount/me").get("data") or {}
        page.goto(ca.get("login_url"), timeout=45000, wait_until="domcontentloaded")
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
                if b.is_visible(timeout=1000):
                    b.click()
                    page.wait_for_timeout(900)
                    break
            except Exception:
                pass
        # open lobby
        try:
            b = page.locator("text=龙之归宿").first
            if b.is_visible(timeout=2000):
                b.click()
                page.wait_for_timeout(3000)
        except Exception:
            pass

        # SEND capture (marker aborted before network)
        try:
            ta = page.locator("textarea").last
            ta.click(timeout=8000)
            ta.fill(MARK, timeout=5000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
            print("composer after send:",
                  repr(ta.input_value()[:40]) if ta.count() else "n/a")
        except Exception as e:
            print("send ERR", str(e)[:110])
        print("captured send calls:", got_send)

        # getUserSettings with captured headers
        try:
            import urllib.request as U
            if sent_headers:
                h = {k: v for k, v in sent_headers.items()
                     if k.lower() in ("authorization", "content-type",
                                       "x-token", "token", "cookie")}
                req = U.Request(
                    "https://chat.mk49.top/api/user/getUserSettings",
                    headers=h, method="GET")
                op = U.build_opener(U.ProxyHandler({}))
                with op.open(req, timeout=15) as resp:
                    print("getUserSettings authed:", resp.read()[:400])
            else:
                print("no headers captured for getUserSettings")
        except Exception as e:
            print("getUserSettings ERR", str(e)[:140])

        # settings menu: click sidebar user avatar (last avatar, sidebar area)
        try:
            av = page.locator(
                "div[class*='sidebar'] [class*='avatar'], "
                "[class*='Sidebar'] [class*='avatar']").last
            av.click(timeout=5000)
            page.wait_for_timeout(1500)
            items = page.eval_on_selector_all(
                "[role='menuitem'], li, [class*='dropdown'] *",
                "els => Array.from(new Set(els.map(e => (e.innerText||'')"
                ".trim().replace(/\\s+/g,' ')).filter(t => t && t.length < 20)))"
                ".slice(0,40)")
            print("avatar menu:", items)
            page.screenshot(path=str(out / "chat_avatar_menu.png"))
        except Exception as e:
            print("avatar menu ERR", str(e)[:110])

        for label in ("设置", "个人资料", "编辑资料", "个人信息", "偏好设置",
                      "Settings", "Profile", "Preferences"):
            try:
                b = page.locator("text=%s" % label).first
                if b.is_visible(timeout=900):
                    b.click()
                    page.wait_for_timeout(2000)
                    t = " ".join(page.inner_text("body").split())[:350]
                    ins = page.eval_on_selector_all(
                        "input, textarea",
                        "els=>els.slice(0,10).map(e=>[e.type||'',e.name||e.id||'',"
                        "e.placeholder||'',(e.value||'').slice(0,24)])")
                    if ins or any(w in t for w in ("昵称", "用户名", "头像",
                                                   "账号", "资料")):
                        print("OPENED", label, "url:", page.url[:110])
                        print(" text:", t)
                        print(" inputs:", ins)
                        page.screenshot(path=str(out / "chat_settings3.png"))
                        break
                    else:
                        print("click", label, "-> no form")
            except Exception:
                pass

        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
