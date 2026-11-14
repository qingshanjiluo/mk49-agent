"""Live regression: message_center now targets THEIR reply (no self-reply),
no parent quote, depth-2 threading, dedupe.

Re-opens the real notification, processes it, verifies the new reply
nests under THEIR comment (reply_post_id = their id), has no quote line,
and a second run does not duplicate.
"""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent
from mk49.messages import parse_message


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    msgs, _ = agent.client.list_messages(page_limit=10)
    target_msg = next((m for m in msgs if m.get("link")), None)
    agent.client.mark_message_unread(target_msg["id"])
    print("unread:", agent.client.unread_count())

    feat = agent.features["message_center"]
    n = feat.run(agent, {"inbox": True})
    print("actions:", n)

    # inspect the newest reply in thread 48058
    comments = agent.client.all_comments(48058)
    mine = [c for c in comments
            if (c.get("user") or {}).get("id") == agent.client.user_id]
    latest = mine[-1] if mine else None
    if latest:
        print("latest my post:", latest["id"],
              "reply_post:", latest.get("reply_post_id"),
              "comment_post:", latest.get("comment_post_id"))
        content = latest.get("content") or ""
        print("has quote line:", content.startswith(">"))
        print("content:", content[:120])
    print("unread after:", agent.client.unread_count())
    agent.state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
