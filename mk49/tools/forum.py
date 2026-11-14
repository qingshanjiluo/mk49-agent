"""Forum toolkit: everything a forum user can do on mk49.top."""
from .base import Tool, schema, jdump


class ReadThreads(Tool):
    name = "forum_read_threads"
    description = ("List threads in a category. Returns id/title/author/"
                   "reply_count/like_count per thread.")
    params = schema({"category_id": ("integer", "category id (2=chat 5=feedback 16=tutorial 36=science 39=fleet, ...)"),
                     "limit": ("integer", "how many, default 10"),
                     "keywords": ("string", "optional search keyword")},
                    required=[])
    danger = False

    def run(self, agent, category_id=None, limit=10, keywords=None):
        threads, total = agent.client.list_threads(
            category_id=category_id, page_limit=min(limit, 30),
            keywords=keywords)
        rows = [{"id": t.get("id"), "title": t.get("title"),
                 "author": (t.get("user") or {}).get("nickname"),
                 "uid": (t.get("user") or {}).get("id"),
                 "replies": t.get("reply_count"), "likes": t.get("like_count"),
                 "pinned": bool(t.get("is_sticky"))} for t in threads]
        return "total=%s\n%s" % (total, jdump(rows))


class ReadThreadDetail(Tool):
    name = "forum_thread_detail"
    description = "Full detail of one thread (body, meta, tags)."
    params = schema({"thread_id": ("integer", "thread id")},
                    required=["thread_id"])

    def run(self, agent, thread_id=0):
        d = agent.client.thread_detail(thread_id) or {}
        keep = {k: d.get(k) for k in (
            "id", "title", "content", "category_id", "user", "posted_at",
            "reply_count", "view_count", "like_count", "is_sticky",
            "is_essence", "thread_tags") if k in d}
        u = keep.get("user") or {}
        keep["author"] = "%s(uid=%s)" % (u.get("nickname"), u.get("id"))
        keep.pop("user", None)
        return jdump(keep)


class ReadComments(Tool):
    name = "forum_read_comments"
    description = ("Read all comments of a thread, fully expanded including "
                   "nested reply chains (depth-marked).")
    params = schema({"thread_id": ("integer", "thread id"),
                     "limit": ("integer", "max comments, default 30")},
                    required=["thread_id"])

    def run(self, agent, thread_id=0, limit=30):
        cs = agent.client.all_comments(thread_id)[:limit]
        rows = []
        for c in cs:
            u = c.get("user") or {}
            rows.append({"id": c.get("id"),
                         "depth": c.get("_depth", 0),
                         "author": "%s(uid=%s)" % (u.get("nickname"),
                                                   u.get("id")),
                         "time": c.get("created_at"),
                         "text": (c.get("content") or "")[:220],
                         "reply_to": c.get("reply_post_id"),
                         "likes": c.get("like_count"),
                         "mine": u.get("id") == agent.client.user_id})
        return jdump(rows)


class LikeThread(Tool):
    name = "forum_like_thread"
    description = "Like (or unlike) a thread."
    params = schema({"thread_id": ("integer", "thread id"),
                     "unlike": ("boolean", "true to cancel like")},
                    required=["thread_id"])
    danger = True

    def run(self, agent, thread_id=0, unlike=False):
        agent.client.like_thread(thread_id, not unlike)
        return "ok: %s thread %s" % ("unliked" if unlike else "liked",
                                     thread_id)


class LikePost(Tool):
    name = "forum_like_comment"
    description = "Like (or unlike) a comment/reply."
    params = schema({"post_id": ("integer", "comment id"),
                     "unlike": ("boolean", "true to cancel like")},
                    required=["post_id"])
    danger = True

    def run(self, agent, post_id=0, unlike=False):
        agent.client.like_post(post_id, not unlike)
        return "ok: %s comment %s" % ("unliked" if unlike else "liked",
                                      post_id)


class CreateThread(Tool):
    name = "forum_create_thread"
    description = ("Publish a new thread. Content is markdown (cards "
                   "[threadcard:id], images ![alt](url), code fences allowed; "
                   "max 10 cards). Safety-checked before send.")
    params = schema({"category_id": ("integer", "category id"),
                     "title": ("string", "thread title, natural, <=30 chars"),
                     "content": ("string", "markdown body")},
                    required=["category_id", "title", "content"])
    danger = True

    def run(self, agent, category_id=2, title="", content=""):
        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(title + "\n" + content, agent)
            if not ok:
                return "BLOCKED by safety: %s" % reason
        title = agent.style.humanize(title, "comment")[:40]
        content = agent.style.humanize(content, "post")
        d = agent.client.create_thread(category_id, title, content)
        if d and d.get("id"):
            agent.state.bump_daily("threads")
            agent.state.stat_bump("threads")
            agent.memory.record_reply(d["id"], d["id"], content)
            return "posted thread %s: %s" % (d["id"], title)
        return "ERROR: create failed"


class EditThread(Tool):
    name = "forum_edit_my_thread"
    description = "Edit my own thread (title/content/category)."
    params = schema({"thread_id": ("integer", "my thread id"),
                     "title": ("string", "new title (optional)"),
                     "content": ("string", "new body (optional)")},
                    required=["thread_id"])
    danger = True

    def run(self, agent, thread_id=0, title=None, content=None):
        fields = {}
        if title:
            fields["title"] = title
        if content:
            fields["content"] = content
        if not fields:
            return "ERROR: nothing to change"
        d = agent.client.modify_thread(thread_id, **fields)
        return "edited thread %s" % thread_id if d else "ERROR: edit failed"


class DeleteThread(Tool):
    name = "forum_delete_my_thread"
    description = "Delete my own thread."
    params = schema({"thread_id": ("integer", "my thread id")},
                    required=["thread_id"])
    danger = True

    def run(self, agent, thread_id=0):
        agent.client.delete_thread(thread_id)
        return "deleted thread %s" % thread_id


class CommentThread(Tool):
    name = "forum_comment"
    description = ("Write a first-level comment on a thread (or a draft "
                   "comment on my own thread). Safety-checked.")
    params = schema({"thread_id": ("integer", "thread id"),
                     "text": ("string", "comment text, casual Chinese")},
                    required=["thread_id", "text"])
    danger = True

    def run(self, agent, thread_id=0, text=""):
        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(text, agent)
            if not ok:
                return "BLOCKED by safety: %s" % reason
        text = agent.style.enforce_length(text, "comment", agent)
        d = agent.client.create_post(thread_id, text)
        if d and d.get("id"):
            agent.state.bump_daily("comments")
            agent.state.stat_bump("comments")
            agent.memory.record_reply(thread_id, d["id"], text)
            return "commented as post %s" % d["id"]
        return "ERROR: comment failed"


class ReplyComment(Tool):
    name = "forum_reply_comment"
    description = ("Nested reply (sub-reply) to any comment or nested reply. "
                   "Threads naturally to any depth. No quoting needed.")
    params = schema({"comment_id": ("integer", "comment/reply id to answer"),
                     "thread_id": ("integer", "thread the comment lives in"),
                     "text": ("string", "reply text")},
                    required=["comment_id", "thread_id", "text"])
    danger = True

    def run(self, agent, comment_id=0, thread_id=0, text=""):
        safety = agent.features.get("content_safety")
        if safety:
            ok, reason, _ = safety.check(text, agent)
            if not ok:
                return "BLOCKED by safety: %s" % reason
        text = agent.style.enforce_length(text, "comment", agent)
        from mk49.context import resolve_reply_target
        comments = agent.client.all_comments(thread_id)
        root_id, nested_id = resolve_reply_target(comments, comment_id)
        d = agent.client.reply_comment(root_id, text,
                                       comment_post_id=nested_id)
        if d and d.get("id"):
            agent.state.bump_daily("comments")
            agent.state.stat_bump("comments")
            return ("replied as post %s (root=%s nested=%s)"
                    % (d["id"], root_id, nested_id))
        return "ERROR: reply failed"


class DeleteComment(Tool):
    name = "forum_delete_my_comment"
    description = "Delete my own comment/reply."
    params = schema({"post_id": ("integer", "my comment id")},
                    required=["post_id"])
    danger = True

    def run(self, agent, post_id=0):
        agent.client.delete_post(post_id)
        return "deleted comment %s" % post_id


class StickyComment(Tool):
    name = "forum_sticky_comment"
    description = "Sticky/unsticky a comment (mine or moderated)."
    params = schema({"post_id": ("integer", "comment id"),
                     "unsticky": ("boolean", "true to cancel")},
                    required=["post_id"])
    danger = True

    def run(self, agent, post_id=0, unsticky=False):
        agent.client.sticky_post(post_id, not unsticky)
        return "ok: %s comment %s" % ("unsticky" if unsticky else "sticky",
                                      post_id)


class ReadInbox(Tool):
    name = "forum_read_inbox"
    description = ("Read my message center: parsed notifications (replies to "
                   "my threads/comments, likes) with located thread ids.")
    params = schema({"limit": ("integer", "max messages, default 10")},
                    required=[])

    def run(self, agent, limit=10):
        from mk49.messages import parse_messages
        msgs, total = agent.client.list_messages(page_limit=min(limit, 30))
        events = parse_messages(msgs)
        rows = [{"kind": e["kind"], "thread": e["thread_id"],
                 "post": e["post_id"], "from": e["from_user_id"],
                 "title": e["title"][:60],
                 "unread": e["unread"],
                 "latest": (e["entries"][-1]["text"][:80]
                            if e["entries"] else "")}
                for e in events]
        return "unread=%s\n%s" % (agent.client.unread_count(), jdump(rows))


class UserProfile(Tool):
    name = "forum_user_profile"
    description = "View a user's profile page data (stats, group, signature)."
    params = schema({"user_id": ("integer", "user id")},
                    required=["user_id"])

    def run(self, agent, user_id=0):
        u = agent.client.get_user(user_id) or {}
        keep = {k: u.get(k) for k in (
            "id", "username", "nickname", "signature", "thread_count",
            "post_count", "follow_count", "fans_count", "liked_count",
            "joined_at", "login_at") if k in u}
        grp = (u.get("group") or {}).get("name")
        keep["group"] = grp
        return jdump(keep)


class MyThreads(Tool):
    name = "forum_my_threads"
    description = "List my own threads (with ids for edit/delete)."
    params = schema({"limit": ("integer", "default 10")}, required=[])

    def run(self, agent, limit=10):
        mine, _ = agent.client.list_threads(user_id=agent.client.user_id,
                                            page_limit=min(limit, 20))
        rows = [{"id": t.get("id"), "title": t.get("title"),
                 "replies": t.get("reply_count"),
                 "created": t.get("created_at")} for t in mine]
        return jdump(rows)


def register_all(reg):
    for t in (ReadThreads(), ReadThreadDetail(), ReadComments(),
              LikeThread(), LikePost(), CreateThread(), EditThread(),
              DeleteThread(), CommentThread(), ReplyComment(),
              DeleteComment(), StickyComment(), ReadInbox(),
              UserProfile(), MyThreads()):
        reg.register(t)
