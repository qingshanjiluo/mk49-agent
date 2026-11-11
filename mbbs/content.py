"""Markdown/HTML content helpers for MBBS (Vditor markdown backend)."""

import html as html_mod
import re

IMG_RE = re.compile(r'<img[^>]+src=["\'](.*?)["\']', re.I | re.S)
URL_RE = re.compile(r'https?://[^\s<>"\')]+', re.I)
EMOJI_RE = re.compile(r":[a-z0-9_]{1,30}:")
CARD_RE = re.compile(r"\[(threadcard|usercard):([1-9]\d*)\]")
POLL_RE = re.compile(r"\[点击编辑投票\]\(mbbs-poll:([^)]+)\)")


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>|</div>|</li>|</h[1-6]>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def extract_image_urls(content):
    urls = IMG_RE.findall(content or "")
    return [u for u in urls if u.startswith(("http://", "https://"))]


def extract_urls(content):
    return URL_RE.findall(content or "")


def has_custom_emoji(content):
    return bool(EMOJI_RE.search(content or ""))


def thread_card(thread_id):
    return "[threadcard:%s]" % thread_id


def user_card(user_id):
    return "[usercard:%s]" % user_id


def poll_placeholder(poll_id):
    return "[点击编辑投票](mbbs-poll:%s)" % poll_id


def inline_image(url, alt="", title=""):
    """Markdown image with optional title/alt (works in Vditor markdown)."""
    if not url:
        return ""
    alt = (alt or "").replace("[", "").replace("]", "")
    if title:
        return "![%s](%s \"%s\")" % (alt, url, title.replace('"', "'"))
    return "![%s](%s)" % (alt, url)


def paragraph(*lines):
    return "\n\n".join(x for x in lines if x)


def quote_block(text):
    return "\n".join("> " + ln for ln in (text or "").splitlines())


def code_block(text, lang=""):
    return "```%s\n%s\n```" % (lang, text)


def truncate(text, limit=200):
    text = strip_html(text) if "<" in (text or "")[:64] else (text or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
