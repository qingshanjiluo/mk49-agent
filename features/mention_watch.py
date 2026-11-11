"""@提及与关键词订阅：被点名或命中订阅词时优先回复。"""

from mbbs.content import strip_html, truncate

from . import Feature, register

DEFAULT_KEYWORDS = ["zzhx", "助手", "机器人", "AI"]


@register
class MentionWatch(Feature):
    name = "mention_watch"
    desc = "@点名/关键词订阅命中时优先定向回复"
    plan_keys = ()          # 观察阶段已收集 mention_hits，主动触发

    def triggered_by(self, plan, agent):
        return bool(agent.obs.mention_hits)

    def run(self, agent, plan):
        done = 0
        keywords = agent.cfg.get("mention_keywords") or DEFAULT_KEYWORDS
        for tid, c in agent.obs.mention_hits[:3]:
            if (c.get("user") or {}).get("id") == agent.client.user_id:
                continue
            plain = strip_html(c.get("content") or "")
            if not any(k.lower() in plain.lower() for k in [agent.username, agent.nickname] + keywords):
                continue
            thread = next((t for t in agent.obs.new_threads if t["id"] == tid), None)
            title = thread.get("title", "") if thread else ""
            try:
                text = agent.llm.reply_to_comment(
                    title, plain,
                    context=truncate((thread or {}).get("_detail", ""), 250),
                    style="对方在直接和你说话，请自然回应。",
                )
            except Exception as exc:
                agent.log("mention llm failed: %s" % exc)
                continue
            text = (text or "").strip()
            if not text:
                continue
            safety = agent.features.get("content_safety")
            if safety:
                ok, reason, _ = safety.check(text, agent)
                if not ok:
                    agent.log("mention reply blocked: %s" % reason)
                    continue
            try:
                data = agent.client.reply_comment(c["id"], text)
            except Exception as exc:
                agent.log("mention reply failed: %s" % exc)
                continue
            if data and data.get("id"):
                agent.state.bump_daily("comments")
                agent.state.stat_bump("comments")
                agent.state.log("mention_reply", "thread=%s post=%s" % (tid, data["id"]))
                agent.log("replied to mention in thread %s" % tid)
                done += 1
        return done
