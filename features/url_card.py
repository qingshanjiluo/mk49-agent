"""链接卡片：抓取在线 URL 的标题/描述并以 markdown 内联进帖子或评论。"""

import re

from mbbs.content import extract_urls

from . import Feature, register

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
DESC_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|og:title)["\'][^>]*'
    r'content=["\'](.*?)["\']', re.I | re.S)
DESC_RE2 = re.compile(
    r'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
    re.I | re.S)

import requests


@register
class UrlCard(Feature):
    name = "url_card"
    desc = "在线 URL 抓标题后内联成预览卡片（发帖/回帖自动增强）"
    plan_keys = ("create_thread", "reply_comment_ids")

    def triggered_by(self, plan, agent):
        return bool(plan.get("create_thread") or plan.get("reply_comment_ids"))

    def enrich(self, text, agent):
        """把文本里的裸 URL 替换成 [标题](url) 形式的可读链接。"""
        urls = extract_urls(text)
        for u in urls[:3]:
            meta = self.fetch_meta(u, agent)
            if meta:
                label = re.sub(r"\s+", " ", meta)[:40]
                text = text.replace(u, "[%s](%s)" % (label, u), 1)
        return text

    @staticmethod
    def fetch_meta(url, agent=None, timeout=12):
        try:
            s = requests.Session()
            s.trust_env = False
            r = s.get(url, timeout=timeout, allow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; mk49-agent/1.0)"})
            if r.status_code != 200:
                return None
            html = r.text[:60000]
            m = TITLE_RE.search(html)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            m2 = DESC_RE.search(html) or DESC_RE2.search(html)
            desc = re.sub(r"\s+", " ", m2.group(1)).strip() if m2 else ""
            return title or desc or None
        except Exception:
            return None

    def run(self, agent, plan):
        return 0  # 由 smart_comment / image_post 调 enrich()
