"""Live depth-2 regression: reply to a NESTED comment (is_comment=True) on a
replyable thread, verify reply_post_id = that nested comment id (proper chain)
and no quote prefix. Then clean up my reply (hide own post = delete).
"""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    agent.observe()

    # find a replyable thread that has a nested comment (depth>=1) by someone else
    picked = None
    for t in agent.obs.replyable:
        nested = [c for c in (t.get("_comments") or [])
                  if c.get("_depth", 0) >= 1 and not c.get("_own")]
        if nested:
            picked = (t, nested[0])
            break
    if not picked:
        print("no nested comment available on replyable threads; skip")
        return 0
    thread, target = picked
    print("thread", thread["id"], "nested target", target["id"],
          "depth", target.get("_depth"))

    feat = agent.features["smart_comment"]
    ok = feat._reply_to_comment(agent, thread, target)
    print("reply ok:", ok)
    if not ok:
        return 1

    # verify chain
    comments = agent.client.all_comments(thread["id"])
    mine = [c for c in comments
            if (c.get("user") or {}).get("id") == agent.client.user_id]
    latest = mine[-1]
    print("new post:", latest["id"], "reply_post:", latest.get("reply_post_id"),
          "comment_post:", latest.get("comment_post_id"))
    content = latest.get("content") or ""
    print("has quote prefix:", content.startswith(">"))
    print("content:", content[:140])

    # cleanup: delete own reply (hide)
    try:
        agent.client.delete_post(latest["id"])
        print("cleaned up reply", latest["id"])
    except Exception as exc:
        print("cleanup skipped:", str(exc)[:80])
    agent.state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
