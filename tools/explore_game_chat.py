"""Explore game.mk49.top (mk49 button) and chat.mk49.top (49chat):
SSO via mk49Token, capture DOM, forms, buttons, screenshots."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def snapshot(page, tag, out_dir):
    page.wait_for_timeout(4000)
    title = page.title()
    print("\n=== %s ===" % tag)
    print("url:", page.url)
    print("title:", title)
    inputs = page.eval_on_selector_all(
        "input, textarea",
        "els=>els.slice(0,15).map(e=>[e.tagName,e.type||'',e.name||e.id||'',"
        "e.placeholder||''])")
    print("inputs:", inputs)
    btns = page.eval_on_selector_all(
        "button, [role=button], a[href]",
        "els=>els.slice(0,25).map(e=>(e.innerText||'').trim()).filter(Boolean)")
    print("buttons:", btns[:25])
    text = page.inner_text("body")[:600].replace("\n", " | ")
    print("text:", text)
    shot = pathlib.Path(out_dir) / ("%s.png" % tag)
    page.screenshot(path=str(shot), full_page=False)
    print("shot:", shot)


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    token = agent.client.token
    uid = agent.client.user_id
    out_dir = pathlib.Path("state/probe")
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        reqs = []
        page.on("request", lambda r: reqs.append(r.url)
                if any(k in r.url for k in ("/api/", "chat", "game", "bbs"))
                else None)

        # --- game ---
        try:
            page.goto("https://game.mk49.top/?mk49Token=%s" % token,
                      timeout=45000, wait_until="domcontentloaded")
            snapshot(page, "game_home", out_dir)
        except Exception as exc:
            print("game ERR", str(exc)[:160])

        # --- chat entry via login_url ---
        try:
            ca = agent.client.get("chatAccount/me").get("data") or {}
            print("\nchat login_url:",
                  (ca.get("login_url") or "")[:120])
            page.goto(ca.get("login_url"), timeout=45000,
                      wait_until="domcontentloaded")
            snapshot(page, "chat_home", out_dir)
        except Exception as exc:
            print("chat ERR", str(exc)[:160])

        print("\n=== API-ish requests seen ===")
        for u in dict.fromkeys(reqs):
            print(" ", u[:140])
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
