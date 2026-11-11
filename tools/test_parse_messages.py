"""Live test of the message parser against real notifications."""
import io
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent
from mk49.messages import parse_messages


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    msgs, total = agent.client.list_messages(page_limit=20)
    events = parse_messages(msgs)
    print("parsed events:", len(events), "of", len(msgs), "raw")
    kinds = {}
    for e in events:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("kinds:", json.dumps(kinds, ensure_ascii=False))
    print("=" * 60)
    for e in events[:10]:
        print("[%s] msg=%s thread=%s post=%s from=%s unread=%s"
              % (e["kind"], e["id"], e["thread_id"], e["post_id"],
                 e["from_user_id"], e["unread"]))
        print("  title:", e["title"][:50])
        for en in e["entries"][:3]:
            print("   -", en["who"], "|", en["action"], "|", en["text"][:60])
    return 0


if __name__ == "__main__":
    sys.exit(main())
