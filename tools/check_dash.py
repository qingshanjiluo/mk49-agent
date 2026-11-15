"""Headless check of the dashboard: capture JS console errors + whether
content actually rendered (blank-page diagnosis)."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright


def main():
    errors = []
    failed = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page()
        pg.on("console", lambda m: errors.append(
            "[%s] %s" % (m.type, m.text)) if m.type in ("error", "warning")
            else None)
        pg.on("pageerror", lambda e: failed.append(str(e)))
        resp = pg.goto("http://127.0.0.1:8899/", timeout=15000,
                       wait_until="networkidle")
        print("HTTP:", resp.status if resp else None)
        pg.wait_for_timeout(2500)
        kpi = pg.inner_text("#kpis") if pg.query_selector("#kpis") else "(missing)"
        log = pg.inner_text("#log") if pg.query_selector("#log") else "(missing)"
        mem = pg.inner_text("#mem") if pg.query_selector("#mem") else "(missing)"
        hbars = pg.eval_on_selector_all("#hbars .col", "els=>els.length")
        print("kpis text len:", len(kpi), "|", kpi.replace("\n", " ")[:120])
        print("log len:", len(log), "|", log.replace("\n", " ")[:80])
        print("mem len:", len(mem), "| mem first:", mem.replace("\n", " ")[:60])
        print("hbars cols:", hbars)
        print("pageerrors:", failed or "none")
        print("console:", errors[:8] or "none")
        pg.screenshot(path=str(pathlib.Path(__file__).parent /
                              "_dash_check.png"), full_page=False)
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
