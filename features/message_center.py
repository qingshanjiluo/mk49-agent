"""Message center watcher: process notifications like a human would -
open the message center, click through to the thread, read the context,
then decide (reply / like / skip) and act. Likes are returned as courtesy.
"""

import time

from mbbs.content import strip_html, truncate

from . import Feature, register

MAX_PER_CYCLE = 5
LIKE_BACK_QUOTA = 10
SKIP_TITLE_WORDS = ("管理日报", "管理公告")


@register
class MessageCenter(Feature):
    name = "message_center"
    desc = "Read inbox, locate threads from notifications, decide reply/like"
    plan_keys = ("inbox",)

    def triggered_by(self, plan, agent):
        return True  # cheap check (unread count) every cycle

    def run(self, agent, plan):
        from mk49.messages import parse_messages

        try:
            unread = agent.client.unread_count()
        except Exception as exc:
            agent.log("inbox unread check failed: %s" % exc)
            return 0
        if not unread:
            return 0
        agent.log("inbox: %d unread" % unread)

        try:
            msgs, _total = agent.client.list_messages(page_limit=10)
        except Exception as exc:
            agent.log("inbox fetch failed: %s" % exc)
            return 0

        from mk49.messages import parse_message
        events = [parse_message(m) for m in msgs
                  if m.get("read_at") is None and m.get("link")]
        done = 0
        likes = 0
        for e in events[:MAX_PER_CYCLE]:
            if any(w in e["title"] for w in SKIP_TITLE_WORDS):
                self._mark(agent, e)
                continue
            acted = self._handle_event(agent, e)
            if acted and acted.get("replied"):
                done += 1
            if acted:
                likes += acted.get("liked", 0)
            self._mark(agent, e)
        if done or likes:
            agent.state.log("inbox", "replies=%s likes=%s" % (done, likes))
        return done + (1 if likes else 0)

    # ---------------------------------------------------------
    def _handle_event(self, agent, e):
        """Locate the thread, read context, decide reply and/or like-back."""
        tid = e["thread_id"]
        try:
            thread = agent.client.thread_detail(tid) or {}
        except Exception as exc:
            agent.log("inbox locate thread %s failed: %s" % (tid, exc))
            return {"replied": False, "liked": 0}
        if thread.get("deleted_at") or thread.get("disable_post"):
            return {"replied": False, "liked": 0}

        comments = []
        try:
            comments = agent.client.all_comments(tid)
        except Exception:
            comments = []

        target = None
        if e["post_id"]:
            target = next((c for c in comments if c.get("id") == e["post_id"]),
                          None)

        result = {"replied": False, "liked": 0}

        # courtesy like-back: they liked my thread/post -> like theirs if visible
        if e["kind"] in ("like_thread", "like_post") and e.get("from_user_id"):
            if self._like_back(agent, e, comments):
                result["liked"] = 1
            return result

        # someone replied to my thread / comment: read and decide
        decision = self._decide(agent, e, thread, comments, target)
        if not decision:
            return result
        if decision.get("action") == "reply" and decision.get("text"):
            text = decision["text"].strip()
            safety = agent.features.get("content_safety")
            if safety:
                ok, reason, _ = safety.check(text, agent)
                if not ok:
                    agent.log("inbox reply blocked: %s" % reason)
                    return result
            payload_ok = True
            try:
                if target is not None:
                    import re as _re
                    from mbbs.render import pretty_comment
                    body = pretty_comment(text, parent_text=truncate(
                        strip_html(target.get("content") or ""), 60),
                        with_quote=True)
                    body = _re.sub(r"\[(?:threadcard|usercard):[1-9]\d*\]",
                                   "", body)
                    data = agent.client.reply_comment(target["id"], body)
                else:
                    data = agent.client.create_post(tid, text)
            except Exception as exc:
                agent.log("inbox reply failed on %s: %s" % (tid, exc))
                payload_ok = False
                data = None
            if payload_ok and data and data.get("id"):
                agent.state.bump_daily("comments")
                agent.state.stat_bump("comments")
                agent.state.log("inbox_reply", "thread=%s post=%s"
                                % (tid, data["id"]))
                agent.log("inbox reply -> thread %s post %s" % (tid, data["id"]))
                result["replied"] = True
        if decision.get("like_target") and target is not None:
            try:
                agent.client.like_post(target["id"], True)
                agent.state.bump_daily("likes")
                agent.state.stat_bump("likes")
                result["liked"] += 1
            except Exception:
                pass
        return result

    def _like_back(self, agent, e, comments):
        """Return the courtesy like when we can find their content."""
        if agent.state.daily_count("likes") >= LIKE_BACK_QUOTA:
            return False
        uid = e.get("from_user_id")
        target = None
        if e.get("post_id"):
            target = next((c for c in comments
                           if c.get("id") == e["post_id"]), None)
        if target is None and uid:
            mine_id = agent.client.user_id
            theirs = [c for c in comments
                      if (c.get("user") or {}).get("id") == uid
                      and not c.get("_own")]
            if theirs:
                target = theirs[-1]
        if target is None:
            return False
        if target.get("is_liked"):
            return False
        try:
            agent.client.like_post(target["id"], True)
            agent.state.bump_daily("likes")
            agent.state.stat_bump("likes")
            agent.state.log("like_back", "post=%s" % target["id"])
            agent.log("liked back post %s" % target["id"])
            return True
        except Exception as exc:
            agent.log("like back failed: %s" % exc)
            return False

    def _decide(self, agent, e, thread, comments, target):
        """LLM decides whether and how to answer this notification."""
        ctx = {
            "kind": e["kind"],
            "thread_title": truncate(thread.get("title") or "", 60),
            "thread_excerpt": truncate(thread.get("content_for_indexes")
                                       or thread.get("content") or "", 300),
            "their_message": e["entries"][0]["text"] if e["entries"] else "",
            "who": e["entries"][0]["who"] if e["entries"] else "",
            "is_reply_to_my_comment": e["kind"] == "reply_comment",
        }
        if target is not None:
            ctx["target_comment"] = truncate(strip_html(target.get("content")
                                                        or ""), 150)
        prompt = (
            "You are the forum agent of mk49.top. A notification arrived. "
            "Decide the action. Output JSON only:\n"
            '{"action":"reply|ignore","text":"<=120 chars Chinese reply",'
            '"like_target":true|false}\n'
            "Rules: reply when they addressed you, asked something, or a "
            "witty comeback fits; a short casual Chinese reply (10-80 chars) "
            "is fine. Ignore only when there is truly nothing to say. Never "
            "reveal being a bot. like_target=true also appreciates their "
            "comment.\n\n"
            "Notification: " + str(ctx)
        )
        # small retry: flash-tier models are inconsistent on borderline
        # notifications; two shots, prefer a reply if either attempt says so
        best = None
        for _ in range(2):
            try:
                d = agent.llm.json(prompt, tier="fast", max_tokens=250,
                                   temperature=0.5)
            except Exception as exc:
                agent.log("inbox decide failed: %s" % exc)
                continue
            if d and d.get("action") == "reply" and d.get("text"):
                return d
            best = best or d
        return best

    @staticmethod
    def _mark(agent, e):
        try:
            agent.client.read_message(e["id"])
        except Exception:
            pass
