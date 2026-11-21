"""Chat send-message capture (route-abort: no real post) + user menu /
settings hunt + forum bbs game-endpoint probe."""
import io
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
    out = pathlib.Path("state/probe")
    out.mkdir(parents=True, exist_ok=True)

    # ---------- A. forum bbs: game-ish endpoints ----------
    print("### forum bbs game endpoints ###")
    for ep in ("gameAccount/me", "gameAccount", "mk49Account/me",
               "user/game", "game/me", "chatAccount"):
        try:
            d = agent.client.get(ep)
            print(" GET %-18s ->" % ep, str(d.get("data"))[:160])
        except Exception as e:
            print(" GET %-18s -> ERR %s" % (ep, str(e)[:90]))

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        captured = []

        def route_h(r):
            if "/api/chat/message" in r.request.url and \
                    r.request.method == "POST":
                captured.append((r.request.method, r.request.url.replace(
                    "https://chat.mk49.top", ""), (r.request.post_data or "")[:300]))
                r.abort()
                return
            r.continue_()
        ctx.route("**/api/**", route_h)

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

        # open group lobby (龙之归宿) - click the 龙 text used earlier
        try:
            b = page.locator("text=龙").first
            if b.is_visible(timeout=1500):
                b.click()
                page.wait_for_timeout(3500)
                print("lobby url:", page.url[:110])
            # fallback: group sidebar entry
            if "group" not in page.url:
                b2 = page.locator("text=龙之归宿").first
                if b2.is_visible(timeout=1500):
                    b2.click()
                    page.wait_for_timeout(3000)
                    print("lobby2 url:", page.url[:110])
        except Exception as e:
            print("lobby ERR", str(e)[:80])

        # type a message into composer, press Enter -> capture then abort
        try:
            ta = page.locator("textarea").last
            ta.click(timeout=8000)
            ta.fill("send-probe-keep",
                    {"timeout": 5000})
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
        except Exception as e:
            print("send ERR", str(e)[:110])
        print("### captured send attempt ###")
        for m, u, d in captured:
            print(" ", m, u, d)
        # anything intercepted?
        try:
            print("composer value now:",
                  page.locator("textarea").last.input_value())
        except Exception:
            pass

        # user menu: click bottom-left avatar then dump menu items
        try:
            page.keyboard.press("Escape")
            page.mouse.wheel(0, 0)
            loc = page.locator("[class*='avatar']").last
            loc.click()
            page.wait_for_timeout(1500)
            items = page.eval_on_selector_all(
                "li, [role='menuitem'], [class*='dropdown'] *, [class*='popover'] *",
                "els => Array.from(new Set(els.map(e => (e.innerText || '')"
                ".trim().replace(/\\s+/g, ' ')).filter(t => t && t.length < 16)))"
                ".slice(0, 40)")
            print("user menu items:", items)
            page.screenshot(path=str(out / "chat_usermenu.png"))
        except Exception as e:
            print("menu ERR", str(e)[:80])

        # hunt 设置 pages
        for label in ("设置", "个人资料", "编辑资料", "个人信息", "账号设置",
                      "Preferences", "Settings", "Profile", "我"):
            try:
                b = page.locator("text=%s" % label).first
                if b.is_visible(timeout=800):
                    b.click()
                    page.wait_for_timeout(1800)
                    t = " ".join(page.inner_text("body").split())[:350]
                    ins = inputs(page)
                    if ins or any(w in t for w in ("昵称", "用户名", "资料",
                                                   "头像", "账号")):
                        print("OPENED [%s] url=%s" % (label, page.url[:110]))
                        print("  text:", t)
                        print("  inputs:", ins)
                        page.screenshot(path=str(out / "chat_settings2.png"))
                        break
                    else:
                        print("clicked %s -> nothing formy" % label)
            except Exception:
                pass

        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
