"""Web toolkit: headless browser (playwright) page reading & interaction."""
from .base import Tool, schema, jdump

_BROWSER = None
_PAGE = None


def _page():
    """Lazy shared headless Chromium page."""
    global _BROWSER, _PAGE
    if _PAGE is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        _BROWSER = pw.chromium.launch(headless=True)
        _PAGE = _BROWSER.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    return _PAGE


class WebOpen(Tool):
    name = "web_open"
    description = ("Open a URL in the headless browser. Returns page title, "
                   "meta description, visible text summary and readiness.")
    params = schema({"url": ("string", "page URL")}, required=["url"])
    max_result = 3000

    def run(self, agent, url=""):
        page = _page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        title = page.title()
        meta = page.eval_on_selector_all(
            "meta[name='description'],meta[property='og:description']",
            "els => els.map(e => e.content)")
        text = page.inner_text("body")
        agent.state.log("web", "open %s" % url[:80])
        return jdump({"url": url, "title": title,
                      "meta": (meta or [""])[0][:200],
                      "text": text[:2400]})


class WebHtml(Tool):
    name = "web_html"
    description = ("Get raw HTML (and optional CSS links) of the current "
                   "page, or of a CSS selector inside it.")
    params = schema({"selector": ("string", "CSS selector, default body"),
                     "with_css": ("boolean", "include stylesheet links")},
                    required=[])

    def run(self, agent, selector="body", with_css=False):
        page = _page()
        el = page.query_selector(selector)
        if el is None:
            return "ERROR: selector not found"
        html = el.inner_html()[:2600]
        out = {"html": html}
        if with_css:
            links = page.eval_on_selector_all(
                "link[rel='stylesheet']", "els => els.map(e => e.href)")
            out["css"] = links[:10]
        return jdump(out)


class WebClick(Tool):
    name = "web_click"
    description = "Click an element on the current page by CSS selector."
    params = schema({"selector": ("string", "CSS selector to click")},
                    required=["selector"])
    danger = True   # can trigger external side effects

    def run(self, agent, selector=""):
        page = _page()
        page.click(selector, timeout=10000)
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        return "clicked %s, title now: %s" % (selector, page.title())


class WebFill(Tool):
    name = "web_fill_form"
    description = ("Fill a form field on the current page "
                   "(input/textarea by selector) without submitting.")
    params = schema({"selector": ("string", "CSS selector of the field"),
                     "text": ("string", "text to type")},
                    required=["selector", "text"])
    danger = True

    def run(self, agent, selector="", text=""):
        page = _page()
        page.fill(selector, text, timeout=10000)
        return "filled %s" % selector


class WebState(Tool):
    name = "web_state"
    description = ("Read current page state: URL, title, visible buttons/"
                   "links/inputs list (for deciding what to interact with).")
    params = schema({}, required=[])

    def run(self, agent):
        page = _page()
        buttons = page.eval_on_selector_all(
            "button, [role=button]",
            "els => els.slice(0,20).map(e => e.innerText.trim())")
        links = page.eval_on_selector_all(
            "a[href]", "els => els.slice(0,20).map(e => [e.innerText.trim(),"
                        " e.getAttribute('href')])")
        inputs = page.eval_on_selector_all(
            "input, textarea",
            "els => els.slice(0,15).map(e => [e.tagName, e.name || e.id,"
            " e.type || ''])")
        return jdump({"url": page.url, "title": page.title(),
                      "buttons": [b for b in buttons if b],
                      "links": links, "inputs": inputs})


def register_all(reg):
    for t in (WebOpen(), WebHtml(), WebClick(), WebFill(), WebState()):
        reg.register(t)
