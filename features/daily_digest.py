"""每日热帖速览：每天定时发一篇汇总帖（threadcard 内联 + 关键词云）。"""

from collections import Counter
from datetime import date

from mbbs.content import thread_card, truncate, strip_html

from . import Feature, register

DIGEST_HOUR = None  # 由 agent 调度判断，此 feature 只在显式触发时执行


@register
class DailyDigest(Feature):
    name = "daily_digest"
    desc = "每日一次的热帖速览/回帖日报（threadcard 内联汇总）"
    plan_keys = ("daily_digest",)

    def triggered_by(self, plan, agent):
        return bool(plan.get("daily_digest"))

    @staticmethod
    def should_run(agent):
        """一天最多一次；用 state.daily 记账。"""
        return agent.state.daily_count("digest") == 0

    def run(self, agent, plan):
        if not self.should_run(agent):
            return 0
        o = agent.obs
        try:
            hot, today, older = fetch_hot_pool(agent)
        except Exception as exc:
            agent.log("hot pool failed: %s" % exc)
            hot, today, older = [], [], []
        if not hot:
            hot = [t for t in o.new_threads][:10]

        # keyword stats from the whole hot pool (not just newest few)
        words = Counter()
        for t in hot:
            for w in _keywords(strip_html(t.get("title") or "")):
                words[w] += 1
        top_words = "、".join(w for w, _ in words.most_common(10)) or "无"

        comment = ""
        try:
            titles = [t.get("title", "") for t in hot[:10]]
            comment = (agent.llm.text(
                "你是论坛速览编辑。根据今天热帖标题，写一句 60 字以内的"
                "当日氛围点评（口语、有梗但克制）。只输出点评正文。\n热帖："
                + " / ".join(titles),
                tier="smart", max_tokens=150) or "").strip()
        except Exception as exc:
            agent.log("digest comment failed: %s" % exc)

        # knowledge tidbit
        kline = ""
        kb_path = agent.cfg.get("knowledge_file") or "state/knowledge.json"
        try:
            import json as _json
            with open(kb_path, "r", encoding="utf-8") as fh:
                items = (_json.load(fh).get("items") or [])[-6:]
            if items:
                pick = items[-2:]
                kline = "**今日冷知识**：" + "；".join(
                    "%s——%s" % (i.get("topic"), truncate(i.get("fact"), 60))
                    for i in pick)
        except (OSError, ValueError):
            pass

        # optional header image
        image_url = ""
        if agent.cfg.get("digest_with_image"):
            try:
                from mk49 import images as img
                prompt = agent.llm.image_prompt_for(
                    "今日论坛热帖速览头图，主题：" + (top_words or "论坛日常"),
                    title="每日热帖速览")
                raw, ext = img.generate(prompt, timeout=120)
                raw, ext = img.fit_for_forum(raw)
                image_url = img.upload_to_forum(
                    agent.client, raw, "digest_%d.%s" % (int(_now()), ext))
                agent.state.stat_bump("images")
            except Exception as exc:
                agent.log("digest image skipped: %s" % exc)

        lines = [
            "## 每日热帖速览 %s" % date.today().isoformat(),
            "",
        ]
        if comment:
            lines += ["> " + comment, ""]
        lines.append("**当日热榜**（浏览/回复/点赞热度）")
        # forum hard cap: max 10 threadcards per post, use 7
        cards_used = 0
        for rank, t in enumerate(hot[:HOT_CARD_LIMIT], 1):
            if cards_used >= HOT_CARD_LIMIT:
                break
            replies = t.get("reply_count", t.get("post_count", 0))
            views = t.get("view_count", 0)
            likes = t.get("like_count", 0)
            lines.append("%d. %s（回复 %s · 浏览 %s · 赞 %s）"
                         % (rank, thread_card(t["id"]),
                            replies, views, likes))
            cards_used += 1
        lines += [
            "",
            "**今日关键词**：%s" % top_words,
        ]
        if kline:
            lines += ["", kline]
        if image_url:
            alt = (top_words or "速览头图").replace("[", "").replace("]", "")[:20]
            lines += ["", "![%s](%s)" % (alt, image_url)]
        lines += [
            "",
            "---",
            "*本帖由驻论坛助手自动汇总，每天晚上更新一次。"
            "想看某帖的详细整理可以在楼下回复我。*",
        ]
        body = "\n".join(lines)
        title = "【速览】%s 当日热帖榜" % date.today().isoformat()

        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(body, agent)
            if not ok:
                agent.log("digest blocked: %s" % reason)
                return 0
        data = agent.client.create_thread(2, title, body)
        if data and data.get("id"):
            agent.state.bump_daily("digest")
            agent.state.stat_bump("digest")
            agent.state.log("digest", str(data["id"]))
            agent.log("digest posted: %s (pool today=%d older=%d)"
                      % (data["id"], len(today), len(older)))
            return 1
        return 0



def _now():
    import time
    return time.time()


HOT_PAGES = 3          # pages per category
HOT_PAGE_SIZE = 20
HOT_CARD_LIMIT = 7     # threadcards per digest post (forum hard cap 10)


def fetch_hot_pool(agent):
    """Multi-page hot pool: pull several pages of every target category,
    rank by heat score (views + replies*10 + likes*15), today first."""
    from datetime import datetime, timedelta, timezone
    cfg = agent.cfg
    cats = list(cfg.get("target_categories") or [2])
    pool = {}
    seen_ids = set()
    # breadth: two sorts x pages so all-time hot & fresh hot both enter
    for cat in cats:
        for sort in ("-created_at", "-view_count", "-posted_at"):
            for page in range(HOT_PAGES):
                try:
                    rows, _ = agent.client.list_threads(
                        category_id=cat, page_limit=HOT_PAGE_SIZE,
                        page_offset=page * HOT_PAGE_SIZE, sort=sort)
                except Exception:
                    rows = []
                for t in rows or []:
                    tid = t.get("id")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        pool[tid] = t
                if not rows:
                    break
    now = datetime.now(timezone.utc)

    def when(t):
        v = t.get("posted_at") or t.get("created_at")
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None

    def score(t):
        return ((t.get("view_count") or 0)
                + (t.get("reply_count") or t.get("post_count") or 0) * 10
                + (t.get("like_count") or 0) * 15)

    today, older = [], []
    cutoff = now - timedelta(hours=24)
    for t in pool.values():
        dt = when(t)
        if t.get("deleted_at") or t.get("is_draft"):
            continue
        if dt and dt >= cutoff:
            today.append(t)
        else:
            older.append(t)
    today.sort(key=score, reverse=True)
    older.sort(key=score, reverse=True)
    # 今日优先；不足 8 条时用近两天的高热帖补足
    hot = today
    if len(hot) < 8:
        hot = hot + [t for t in older if t.get("id") not in
                     {x.get("id") for x in hot}][: 8 - len(hot)]
    return hot[:12], today, older


_CUT = set("的了是在和与及我你他她它们这那个一二三四五六七八九十上下中有没都还就")


def _keywords(text):
    out, buf = [], ""
    for ch in text:
        if "一" <= ch <= "鿿" and ch not in _CUT:
            buf += ch
        else:
            if len(buf) >= 2:
                out.append(buf)
            buf = ""
    if len(buf) >= 2:
        out.append(buf)
    return out
