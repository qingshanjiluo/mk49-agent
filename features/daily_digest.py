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

        lines = [
            "## 📋 今日速览 %s" % date.today().isoformat(),
            "",
            "**热帖一览**",
        ]
        # 论坛限制：一篇帖子最多 10 个站内卡片，列表最多放 7 张
        cards_used = 0
        for t in o.new_threads[:7]:
            if cards_used >= 7:
                break
            lines.append("- [threadcard:%s] %s" % (t["id"], truncate(t.get("title", ""), 30)))
            cards_used += 1
        lines += [
            "",
            "**今日关键词**：%s" % top_words,
            "",
            "> 本帖由驻论坛助手自动汇总，每天更新一次。",
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
