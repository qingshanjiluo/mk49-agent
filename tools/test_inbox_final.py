"""Full end-to-end test: mark a notification unread, then run the whole
message_center feature, expecting a real reply + like-back + mark-as-read."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    msgs, _ = agent.client.list_messages(page_limit=10)
    target = next((m for m in msgs if m.get("link")), None)
    agent.client.mark_message_unread(target["id"])
    print("unread:", agent.client.unread_count())

    feat = agent.features["message_center"]
    n = feat.run(agent, {"inbox": True})
    print("actions:", n)
    print("unread after:", agent.client.unread_count())
    agent.state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
