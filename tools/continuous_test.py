"""Full continuous real test: two consecutive cycles, reporting everything."""
import io
import json
import sys
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    for cycle in (1, 2):
        print("=" * 55)
        print("CYCLE", cycle)
        ran = agent.run_cycle()
        print("ran:", ran)
        print("unread:", agent.client.unread_count())
        time.sleep(8)
    agent.state.save()
    d = agent.state.data
    print("=" * 55)
    print("daily:", json.dumps(d.get("daily", {}), ensure_ascii=False))
    print("stats:", json.dumps(d.get("stats", {}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
