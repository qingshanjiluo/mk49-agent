"""Full live test of message_center.run() with a synthetic unread message.

Marks one old notification unread, then runs the feature end-to-end:
parse -> locate -> decide -> (reply/like) -> mark read.
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
    msgs, _ = agent.client.list_messages(page_limit=5)
    target = msgs[0]
    print("re-opening msg", target["id"], "-", target["title"][:40])
    agent.client.mark_message_unread(target["id"])
    print("unread now:", agent.client.unread_count())

    feat = agent.features["message_center"]
    n = feat.run(agent, {"inbox": True})
    print("message_center actions:", n)
    print("unread after:", agent.client.unread_count())
    agent.state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
