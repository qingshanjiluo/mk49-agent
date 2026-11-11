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
        titles = o.hot_titles[:12] or ["（今日无新帖）"]
        ids = [t["id"] for t in o.new_threads[:8]]

        # 关键词统计
        words = Counter()
        for t in o.new_threads:
            for w in _keywords(strip_html(t.get("title") or "")):
                words[w] += 1
        top_words = "、".join(w for w, _ in words.most_common(8)) or "无"

        # AI 一句点评（今日氛围/热点）
        comment = ""
        try:
            comment = (agent.llm.text(
                "你是论坛速览的编辑。根据今天的热帖标题，写一句 60 字以内的"
                "当日论坛氛围点评（口语、有梗但克制）。只输出点评正文。\n热帖："
                + " / ".join(titles[:10]),
                tier="smart", max_tokens=150) or "").strip()
        except Exception as exc:
            agent.log("digest comment failed: %s" % exc)

        # 知识碎片（来自知识库）
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

        # 可选配图（生图失败静默跳过）
        image_url = ""
        if agent.cfg.get("digest_with_image"):
            try:
                from mk49 import images as img
                prompt = agent.llm.image_prompt_for(
                    "今日论坛速览头图，主题：" + (top_words or "论坛日常"),
                    title="每日速览")
                raw, ext = img.generate(prompt, timeout=120)
                raw, ext = img.fit_for_forum(raw)
                image_url = img.upload_to_forum(
                    agent.client, raw, "digest_%d.%s" % (int(_now()), ext))
                agent.state.stat_bump("images")
            except Exception as exc:
                agent.log("digest image skipped: %s" % exc)

        lines = [
            "## 📋 今日速览 %s" % date.today().isoformat(),
            "",
        ]
        if comment:
            lines += ["> " + comment, ""]
        lines.append("**热帖一览**")
        # 论坛限制：一篇帖子最多 10 个站内卡片，列表最多放 7 张
        cards_used = 0
        for t in o.new_threads[:7]:
            if cards_used >= 7:
                break
            replies = t.get("reply_count", t.get("post_count", "?"))
            lines.append("- %s %s（回复 %s）"
                         % (thread_card(t["id"]),
                            truncate(t.get("title", ""), 26), replies))
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
            "*本帖由驻论坛助手自动汇总，每天更新一次。想看某帖的详细整理可以在楼下回复我。*",
        ]
        body = "\n".join(lines)
        title = "【速览】%s 热帖与关键词" % date.today().isoformat()

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
            agent.log("digest posted: %s" % data["id"])
            return 1
        return 0


def _now():
    import time
    return time.time()


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
