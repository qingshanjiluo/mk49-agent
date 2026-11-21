"""Chat settings / nickname edit surface probe + game main-page capture."""
import io
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def inputs(page, n=12):
    return page.eval_on_selector_all(
        "input, textarea",
        "els => els.slice(0, %d).map(e => [e.type || '', e.name || e.id || '', "
        "e.placeholder || '', (e.value || '').slice(0, 24)])" % n)


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    token = agent.client.token
    out = pathlib.Path("state/probe")
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        api = []

        def on_req(r):
            if "/api/" in r.url:
                api.append((r.method, r.url.replace("https://chat.mk49.top", ""),
                            (r.post_data or "")[:180]))
        page.on("request", on_req)

        # ---- GAME main: block popup navigation to about:blank ----
        print("### GAME main ###")
        try:
            page.add_init_script(
                "window.addEventListener('beforeunload', e => { if("
                "(location.origin||'') === '' ) e.preventDefault(); });")
            page.goto("https://game.mk49.top/?mk49Token=" + token,
                      timeout=45000, wait_until="commit")
            page.wait_for_timeout(9000)
            print("url:", page.url[:100])
            if not page.url.startswith("about:"):
                print("title:", page.title())
                t = " ".join(page.inner_text("body").split())[:400]
                print("text:", t)
                ins = inputs(page)
                print("inputs:", ins)
                page.screenshot(path=str(out / "game_main.png"))
        except Exception as exc:
            print("game ERR", str(exc)[:140])

        # ---- CHAT: login, skip tour, hunt settings ----
        print("\n### CHAT settings hunt ###")
        api.clear()
        try:
            ca = agent.client.get("chatAccount/me").get("data") or {}
            page.goto(ca.get("login_url"), timeout=45000,
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
                    if b.is_visible(timeout=1000):
                        b.click()
                        page.wait_for_timeout(900)
                        break
                except Exception:
                    pass

            # click avatar / nickname to open user menu
            menu_txt = ""
            for sel in ("[class*='avatar'] img", "[class*='avatar']", "text=龙"):
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=1200):
                        loc.click()
                        page.wait_for_timeout(1600)
                        menu_txt = " ".join(page.inner_text("body").split())[:400]
                        print("menu after %s ->" % sel, menu_txt[:240])
                        if any(w in menu_txt for w in ("设置", "资料", "退出")):
                            break
                except Exception:
                    pass

            # click 设置 / 个人资料 if present in menu
            for label in ("个人资料", "编辑资料", "设置", "个人信息", "Profile"):
                try:
                    b = page.locator("text=%s" % label).first
                    if b.is_visible(timeout=900):
                        b.click()
                        page.wait_for_timeout(2200)
                        print("opened:", label, "| url:", page.url[:110])
                        t = " ".join(page.inner_text("body").split())[:400]
                        print("panel:", t)
                        print("inputs:", inputs(page))
                        page.screenshot(path=str(out / "chat_settings.png"))
                        break
                except Exception:
                    pass

            # getUserSettings response body via API fetch in page context
            try:
                data = page.evaluate(
                    "fetch('/api/user/getUserSettings',{headers:"
                    "{'content-type':'application/json'},method:'GET'})"
                    ".then(r=>r.text())")
                print("getUserSettings raw:", data[:500])
            except Exception as e:
                print("getUserSettings ERR", str(e)[:100])

            # does user info contain nickname? try getUserInfoList self
            try:
                info = page.evaluate(
                    "fetch('/api/user/getUserInfoList',{headers:"
                    "{ 'content-type': 'application/json'},"
                    "method:'POST',body:JSON.stringify({userIds:['self']})})"
                    ".then(r=>r.text())")
                print("selfInfo:", info[:300])
            except Exception as e:
                print("selfInfo ERR", str(e)[:100])
        except Exception as exc:
            print("chat ERR", str(exc)[:140])

        print("\n### API ###")
        for m, u, d in list(dict.fromkeys(api))[:50]:
            print(" %-4s %s %s" % (m, u, d[:110]))
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
