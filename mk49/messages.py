"""Structured message parsing for the mk49 agent: turn raw notifications into
typed, locatable events, then act on them (reply / like / read)."""

import re

LINK_RE = re.compile(r"/#/thread/detail/(\d+)")
POST_KEY_RE = re.compile(r"post(\d+)")
LIKE_KEY_RE = re.compile(r"\.setLike$")

# content is a merged block: "YYYY-MM-DD HH:MM:SS\n用户\"nick\"回复了你的(帖子|评论):\ntext"
ENTRY_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\n"
    r"用户\"(.+?)\"(回复了你的帖子|回复了你帖子里的评论|回复了你的评论|点赞了你的帖子|赞了你的评论)[:：]?\s*\n?"
    r"(.*)",
    re.S,
)


def parse_message(m):
    """Return a structured event dict for one raw notification."""
    title = (m.get("title") or "").strip()
    content = (m.get("content") or "").strip()
    link = m.get("link") or ""
    thread_id = None
    lm = LINK_RE.search(link)
    if lm:
        thread_id = int(lm.group(1))

    kind = "unknown"
    if "有了新的回复" in title:
        kind = "reply_comment"
    elif "有了新的评论" in title or "有了新的回复" in title:
        kind = "reply_thread"
    if "被点赞了" in title:
        kind = "like_thread"
    if "赞了你的评论" in title or ("评论" in title and "被赞" in title):
        kind = "like_post"
    if "回复了你帖子里的评论" in content and kind == "unknown":
        kind = "reply_thread"

    # refine with content when the title is ambiguous
    if kind == "unknown":
        if "回复了你的评论" in content:
            kind = "reply_comment"
        elif "回复了你的帖子" in content:
            kind = "reply_thread"
        elif "点赞" in content:
            kind = "like_thread"

    entries = []
    for mm in ENTRY_RE.finditer(content):
        entries.append({
            "time": mm.group(1),
            "who": mm.group(2),
            "action": mm.group(3),
            "text": (mm.group(4) or "").strip()[:200],
        })

    # specific post when the merge key carries it (viewThread48558.post480693)
    post_id = None
    key = m.get("unread_merge_key") or ""
    pm = POST_KEY_RE.search(key)
    if pm:
        post_id = int(pm.group(1))

    return {
        "id": m.get("id"),
        "kind": kind,
        "thread_id": thread_id,
        "post_id": post_id,
        "from_user_id": m.get("from_user_id"),
        "title": title,
        "entries": entries,
        "unread": m.get("read_at") is None,
        "raw": m,
    }


def parse_messages(raw_list):
    events = [parse_message(m) for m in raw_list]
    return [e for e in events if e["thread_id"]]
