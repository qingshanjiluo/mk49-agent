"""Smart commenting: first-level comments, nested replies (楼中楼) and
replies-to-replies.

Guards enforced before any write:
  - never write inside a pinned thread or a veteran author's thread
    (those are filtered out of obs.replyable by the agent already)
  - never reply to my own comment
  - never exceed max_reply_depth
Every generated body goes through content_safety first.
"""

from mbbs import render
from mbbs.content import strip_html, truncate

from mk49.context import comment_chain, thread_meta

from . import Feature, register

MAX_PER_CYCLE = 6


@register
class SmartComment(Feature):
    name = "smart_comment"
    desc = "Auto comment + nested 楼中楼 replies with reply-chain context"
    plan_keys = ("reply_targets",)

    def triggered_by(self, plan, agent):
        return bool(plan.get("reply_targets"))

    def run(self, agent, plan):
        done = 0
        for target in (plan.get("reply_targets") or [])[:MAX_PER_CYCLE]:
            try:
                tid = int(target.get("thread") or 0)
                pid = int(target.get("post") or 0)
            except (TypeError, ValueError):
                continue
            thread = next((t for t in agent.obs.replyable if t.get("id") == tid), None)
            if not thread:
                continue
            if pid:
                comment = next((c for c in (thread.get("_comments") or [])
                                if c.get("id") == pid), None)
                if not comment or comment.get("_own"):
                    continue
                depth = int(comment.get("_depth") or 0)
                if depth >= int(agent.cfg.get("max_reply_depth", 3)):
                    continue
                if self._reply_to_comment(agent, thread, comment):
                    done += 1
            else:
                if self._already_commented_today(agent, thread):
                    when = self._last_comment_time(agent, thread) or "earlier today"
                    agent.log("WARNING: thread %s already has your comment "
                              "(%s) - think twice before commenting again"
                              % (tid, when))
                    continue
                if self._comment_thread(agent, thread):
                    done += 1
        return done

    def _last_comment_time(self, agent, thread):
        """Return ISO time of my newest comment on this thread, or None."""
        from datetime import datetime
        seq = (agent.memory.state.data.get("thread_memory") or {}).get(
            str(thread.get("id"))) or []
        newest = None
        for e in seq:
            if e.get("kind") == "mine" and e.get("ts"):
                newest = max(newest or 0, e["ts"])
        if not newest:
            return None
        return datetime.fromtimestamp(newest).strftime("%m-%d %H:%M")

    def _already_commented_today(self, agent, thread):
        from datetime import date
        seq = (agent.memory.state.data.get("thread_memory") or {}).get(
            str(thread.get("id"))) or []
        for e in reversed(seq):
            if e.get("kind") == "mine":
                from datetime import datetime as _dt
                return _dt.fromtimestamp(e["ts"]).date() == date.today()
        return False

    def _reply_to_comment(self, agent, thread, comment):
        parent = strip_html(comment.get("content") or "")
        chain = comment_chain(thread.get("_comments") or [], comment, agent.client.user_id)
        text = agent.llm.reply_to_reply(
            thread.get("title") or "",
            thread.get("_detail") or "",
            parent,
            chain=chain,
            my_nickname=agent.nickname,
            category=agent.obs.category_names.get(thread.get("category_id"), ""),
            meta=thread_meta(thread, agent.obs.category_names, agent.client.user_id),
        )
        text = (text or "").strip()
        if not text or not self._gate(agent, text):
            return False
        text = agent.style.enforce_length(text, "comment", agent)
        import re as _re
        payload = render.shorten_comment_md(
            _re.sub(r"\[(?:threadcard|usercard):[1-9]\d*\]", "", text))
        from mk49.context import resolve_reply_target
        root_id, nested_id = resolve_reply_target(
            thread.get("_comments") or [], comment["id"])
        data = None
        try:
            data = agent.client.reply_comment(root_id, payload,
                                              comment_post_id=nested_id)
        except Exception as exc:
            agent.log("nested reply failed on %s: %s" % (comment["id"], exc))
        if data and data.get("id"):
            agent.memory.record_reply(thread["id"], data["id"], text)
            agent.memory.record_their_reply(
                thread["id"], comment["id"],
                (comment.get("user") or {}).get("nickname"),
                (comment.get("user") or {}).get("id"), parent)
        return self._after_write(agent, thread, data, "nested-reply")

    # ------------------------------------------------------------- helpers
    def _after_write(self, agent, thread, data, kind):
        if not data or not data.get("id"):
            return False
        agent.state.bump_daily("comments")
        agent.state.stat_bump("comments")
        agent.state.log("comment", "%s thread=%s post=%s"
                        % (kind, thread["id"], data["id"]))
        agent.log("%s -> thread %s post %s" % (kind, thread["id"], data["id"]))
        return True

    @staticmethod
    def _gate(agent, text):
        safety = agent.features.get("content_safety")
        if not safety:
            return True
        ok, _reason, _ = safety.check(text, agent)
        if not ok:
            agent.log("content_safety blocked comment")
            agent.state.log("safety_block", str(_reason)[:120])
        return ok
