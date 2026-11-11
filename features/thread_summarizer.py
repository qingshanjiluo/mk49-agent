"""长帖摘要：帖子过长时，把 LLM 摘要作为评论补在楼下（方便后来者）。"""

from mbbs.content import strip_html, truncate

from . import Feature, register

MIN_LEN = 1200


@register
class ThreadSummarizer(Feature):
    name = "thread_summarizer"
    desc = "超长帖自动追加 3 行要点摘要评论"
    plan_keys = ("reply_comment_ids",)

    def triggered_by(self, plan, agent):
        return bool(agent.obs.new_threads)

    def run(self, agent, plan):
        done = 0
        for t in agent.obs.new_threads[:4]:
            content = t.get("_detail") or ""
            if len(content) < MIN_LEN:
                continue
            if str(t.get("id")) in agent.state.data.get("summarized_threads", []):
                continue
            # 已有摘要则跳过
            existing = agent.obs.thread_comments.get(t["id"], [])
            if any("📌 摘要" in strip_html(c.get("content") or "") for c in existing):
                continue
            if any((c.get("user") or {}).get("id") == agent.client.user_id
                   for c in existing):
                agent.state.data.setdefault("summarized_threads", []).append(str(t["id"]))
                continue
            try:
                summary = agent.llm.text(
                    "用3行以内总结这个长帖的要点（每行一个要点，以 - 开头）：\n《%s》\n%s"
                    % (truncate(t.get("title", ""), 40), content[:3000]),
                    max_tokens=350,
                )
            except Exception as exc:
                agent.log("summarize failed: %s" % exc)
                continue
            body = "📌 摘要（自动整理）：\n" + (summary or "").strip()
            safety = agent.features.get("content_safety")
            if safety:
                ok, reason, _ = safety.check(body, agent)
                if not ok:
                    continue
            try:
                data = agent.client.create_post(t["id"], body)
            except Exception as exc:
                agent.log("summary post failed: %s" % exc)
                continue
            if data and data.get("id"):
                agent.state.data.setdefault("summarized_threads", []).append(str(t["id"]))
                agent.state.bump_daily("comments")
                agent.state.log("summary", "thread=%s" % t["id"])
                agent.log("summary posted in thread %s" % t["id"])
                done += 1
        return done
