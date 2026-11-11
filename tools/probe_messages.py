"""Inspect the message center: full shapes of unread notifications."""
import io
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    msgs, total = agent.client.list_messages(page_limit=20)
    print("total:", total, "fetched:", len(msgs))
    types = {}
    for m in msgs:
        t = m.get("type")
        types[t] = types.get(t, 0) + 1
    print("types:", json.dumps(types, ensure_ascii=False))
    print("=" * 60)
    for m in msgs[:8]:
        print(json.dumps(m, ensure_ascii=False, indent=1)[:900])
        print("-" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
