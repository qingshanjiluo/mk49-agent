"""Deep exploration round 2: (1) game.mk49.top full load + in-game chat/name
edit UI, (2) chat.mk49.top auto-login then account/profile/message surface."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def dom_report(page, tag, out_dir, settle=6000):
    try:
        page.wait_for_load_state("networkidle", timeout=settle)
    except Exception:
        pass
    page.wait_for_timeout(2500)
    print("\n=== %s ===" % tag)
    print("url:", page.url[:160])
    try:
        print("title:", page.title())
    except Exception as e:
        print("title ERR:", str(e)[:80])
    try:
        inputs = page.eval_on_selector_all(
            "input, textarea, [contenteditable=true]",
            "els=>els.slice(0,20).map(e=>[e.tagName,e.type||e.getAttribute('contenteditable')||'',"
            "e.name||e.id||'',e.placeholder||e.getAttribute('data-ph')||''])")
        print("inputs(%d):" % len(inputs))
        for row in inputs:
            print("   ", row)
    except Exception as e:
        print("inputs ERR", str(e)[:100])
    try:
        btns = page.eval_on_selector_all(
            "button, [role=button], a[href]",
            "els=>Array.from(new Set(els.map(e=>(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,24))))"
            ".filter(Boolean).slice(0,30)")
        print("buttons:", btns)
    except Exception:
        pass
    try:
        txt = page.inner_text("body")[:900].replace("\n", " | ")
        print("text:", txt)
    except Exception:
        pass
    shot = pathlib.Path(out_dir) / ("%s.png" % tag)
    try:
        page.screenshot(path=str(shot), full_page=False)
        print("shot:", shot)
    except Exception:
        pass


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
        api_seen = []
        page.on("request", lambda r: api_seen.append(r.url)
                if "/api/" in r.url or "gateway" in r.url else None)

        # --- 1. game: wait load then snapshot ---
        try:
            page.goto("https://game.mk49.top/?mk49Token=%s" % token,
                      timeout=60000, wait_until="load")
            page.wait_for_timeout(6000)
            dom_report(page, "game_loaded", out_dir)
            # look for chat / name edit UI (click common HUD elements)
            for sel in ["text=聊天", "text=消息", "text=名字", "text=昵称",
                        "text=发言", "text=开始", "text=进入游戏", "text=Play"]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=1500):
                        print("visible:", sel)
                except Exception:
                    pass
        except Exception as exc:
            print("game ERR", str(exc)[:160])

        # --- 2. chat: auto login ---
        try:
            ca = agent.client.get("chatAccount/me").get("data") or {}
            page.goto(ca.get("login_url"), timeout=60000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(3500)
            # click login if form visible
            try:
                btn = page.locator("button:has-text('登录')").first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    page.wait_for_timeout(5000)
                    print("clicked login")
            except Exception:
                pass
            dom_report(page, "chat_logged_in", out_dir, settle=8000)
        except Exception as exc:
            print("chat ERR", str(exc)[:160])

        print("\n=== API requests ===")
        for u in list(dict.fromkeys(api_seen))[:40]:
            print(" ", u[:150])
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
