"""把帖子/评论原始数据渲染成带元数据的可读文本，供 LLM 阅读与决策。

论坛 API 返回的字段很散（user 嵌套、时间是 ISO、层级靠 is_comment/reply_post_id），
这里统一压成"人话元数据"，让模型一眼看清：谁发的、什么时候、几楼、回给谁、
是不是我自己发的、能不能回。
"""

from datetime import datetime

from mbbs.content import strip_html, truncate

UNKNOWN = "?"


def fmt_time(iso):
    if not iso:
        return "未知时间"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return str(iso)[:16]


def author_of(obj):
    """帖子/评论统一下的作者信息 -> (nickname, user_id, username, group)。"""
    if not isinstance(obj, dict):
        return UNKNOWN, None, "", ""
    user = obj.get("user") or {}
    if not user and obj.get("user_id"):
        return UNKNOWN, obj.get("user_id"), "", ""
    grp = (user.get("group") or {}).get("name") or ""
    return (user.get("nickname") or user.get("username") or UNKNOWN,
            user.get("id"), user.get("username") or "", grp)


def thread_meta(t, category_names=None, my_id=None):
    """帖子级元数据，一行式。"""
    nick, uid, uname, grp = author_of(t)
    cat_id = t.get("category_id")
    cat = (category_names or {}).get(cat_id, "板块%s" % cat_id)
    own = "（我发的）" if (my_id and uid == my_id) else ""
    flags = []
    if t.get("is_sticky"):
        flags.append("置顶")
    if t.get("is_essence"):
        flags.append("精华")
    if t.get("disable_post"):
        flags.append("禁回")
    if t.get("is_draft"):
        flags.append("草稿")
    return ("《%s》 id=%s | 板块:%s | 作者:%s(uid=%s%s%s) | %s | "
            "回复:%s 浏览:%s 赞:%s%s" % (
                truncate(t.get("title") or "", 40), t.get("id"), cat,
                nick, uid, (" " + grp) if grp else "", own,
                fmt_time(t.get("posted_at") or t.get("created_at")),
                t.get("reply_count", t.get("post_count", "?")),
                t.get("view_count", "?"), t.get("like_count", 0),
                (" | " + "/".join(flags)) if flags else ""))


def comment_meta(c, seq=None, my_id=None, category_names=None):
    """评论级元数据：楼层、作者、时间、层级（楼中楼/一级）、是否我的。"""
    nick, uid, uname, grp = author_of(c)
    own = "（我）" if (my_id and uid == my_id) else ""
    if c.get("is_comment"):
        level = "楼中楼→回复#%s" % (c.get("reply_post_id") or "?")
    else:
        level = "一级评论"
    head = "#%s楼 " % seq if seq is not None else ""
    return "%s%s %s(uid=%s%s) %s [%s]" % (
        head, level, nick, uid, own,
        fmt_time(c.get("created_at")), truncate(strip_html(c.get("content") or ""), 160),
    )


def comment_chain(comments, target, my_id=None):
    """把目标评论到一级楼的链路拼出来（谁回给谁），供楼中楼决策。"""
    by_id = {c.get("id"): c for c in comments}
    chain = []
    cur = target
    guard = 0
    while cur and guard < 6:
        chain.append(cur)
        parent_id = cur.get("reply_post_id") or cur.get("_parent_id")
        cur = by_id.get(parent_id)
        guard += 1
    chain.reverse()
    return " ← ".join(
        "%s(%s)" % (author_of(c)[0], truncate(strip_html(c.get("content") or ""), 40))
        for c in chain
    )


def is_replyable(t, cfg, my_id):
    """能否对这个帖子发起评论/楼中楼。返回 (bool, reason)。"""
    if not t:
        return False, "no thread"
    if t.get("deleted_at") or t.get("is_draft"):
        return False, "draft/deleted"
    if t.get("disable_post"):
        return False, "disabled"
    if t.get("is_sticky") and cfg.get("skip_pinned", True):
        return False, "pinned"
    nick, uid, uname, grp = author_of(t)
    if my_id and uid == my_id:
        return False, "own thread"
    floor = int(cfg.get("skip_authors_below_id", 50) or 0)
    if floor and uid is not None and isinstance(uid, int) and uid < floor:
        return False, "author id %s < %s (forum veteran)" % (uid, floor)
    return True, ""


def render_thread_block(t, comments, cfg, my_id, category_names=None,
                        body="", max_comments=8):
    """给 LLM 的完整帖子阅读块（元数据 + 正文 + 楼层元数据）。"""
    lines = [thread_meta(t, category_names, my_id)]
    ok, why = is_replyable(t, cfg, my_id)
    lines.append("可回复: %s%s" % ("是" if ok else "否", "" if ok else "（%s）" % why))
    if body:
        lines.append("正文: " + truncate(body, 700))
    if comments:
        lines.append("楼层(%d):" % len(comments))
        for i, c in enumerate(comments[-max_comments:], 1):
            lines.append("  " + comment_meta(c, len(comments) - max_comments + i
                                             if len(comments) > max_comments else i,
                                             my_id))
    else:
        lines.append("楼层: 暂无")
    return "\n".join(lines)
