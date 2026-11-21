"""Explore round 3:
- chat.mk49.top: skip tour -> sidebar/nav dump -> settings name edit field
  (capture API, read-only) -> conversations/channels list
- game.mk49.top: full navigation trace (frame/redirect aware)
"""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    token = agent.client.token
    out_dir = pathlib.Path("state/probe")
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        api = []
        page.on("request", lambda r: api.append((r.method, r.url,
                 (r.post_data or "")[:120]))
                if "/api/" in r.url else None)

        # ---------- GAME navigation trace ----------
        print("### GAME trace ###")
        try:
            page.goto("https://game.mk49.top/?mk49Token=%s" % token,
                      timeout=45000, wait_until="commit")
            for i in range(8):
                page.wait_for_timeout(2500)
                try:
                    print(" t=%ds url=%s title=%s"
                          % (i * 2 + 2, page.url[:90], page.title()[:40]))
                except Exception as e:
                    print(" t=%ds ERR %s" % (i * 2 + 2, str(e)[:60]))
                if page.url.startswith("about:"):
                    break
            if not page.url.startswith("about:"):
                page.wait_for_timeout(4000)
                try:
                    print(" game text:", page.inner_text("body")[:400].replace("\n", " | "))
                    page.screenshot(path=str(out_dir / "game2.png"))
                except Exception as e:
                    print(" game snap ERR", str(e)[:80])
        except Exception as exc:
            print("game ERR", str(exc)[:160])

        # ---------- CHAT deep ----------
        print("\n### CHAT deep ###")
        api.clear()
        try:
            ca = agent.client.get("chatAccount/me").get("data") or {}
            page.goto(ca.get("login_url"), timeout=45000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            try:
                btn = page.locator("button:has-text('登录')").first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    page.wait_for_timeout(4500)
            except Exception:
                pass
            # skip onboarding tour
            for label in ("跳过引导", "跳过", "下一步", "开始使用"):
                try:
                    b = page.locator("button:has-text('%s')" % label).first
                    if b.is_visible(timeout=1200):
                        b.click()
                        page.wait_for_timeout(1200)
                        print("clicked", label)
                        break
                except Exception:
                    pass
            # sidebar/nav text
            try:
                navs = page.eval_on_selector_all(
                    "nav *, aside *, [class*=sidebar] *",
                    "els=>Array.from(new Set(els.map(e=>(e.innerText||'').trim().replace(/\\s+/g,' ')).filter(t=>t&&t.length<20))).slice(0,40)")
                print("nav items:", navs)
            except Exception as e:
                print("nav ERR", str(e)[:80])

            # click 私信 (conversations)
            try:
                b = page.locator("text=私信").first
                if b.is_visible(timeout=1500):
                    b.click()
                    page.wait_for_timeout(3000)
                    print("opened 私信, url:", page.url[:110])
                    print("conv text:", page.inner_text("body")[:500].replace("\n", " | "))
            except Exception as e:
                print("私信 ERR", str(e)[:80])

            # open profile/settings via avatar (click user name 龙)
            try:
                b = page.locator("text=龙").first
                if b.is_visible(timeout=1500):
                    b.click()
                    page.wait_for_timeout(2500)
                    print("profile click -> url:", page.url[:110])
                    print("profile text:", page.inner_text("body")[:700].replace("\n", " | "))
                    inputs = page.eval_on_selector_all(
                        "input, textarea",
                        "els=>els.slice(0,12).map(e=>[e.type||'',e.name||e.id||'',e.placeholder||'',(e.value||'').slice(0,20)])")
                    print("profile inputs:", inputs)
                    page.screenshot(path=str(out_dir / "chat_profile.png"))
            except Exception as e:
                print("profile ERR", str(e)[:80])

            page.screenshot(path=str(out_dir / "chat_nav.png"))
        except Exception as exc:
            print("chat ERR", str(exc)[:160])

        print("\n### CHAT API calls ###")
        for m, u, d in list(dict.fromkeys(api))[:60]:
            print(" %-4s %s %s" % (m, u.replace("https://chat.mk49.top", ""), d[:70]))
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
