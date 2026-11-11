"""Fetch the just-posted digest thread to verify rendering content."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    detail = agent.client.thread_detail(48702) or {}
    print("title:", detail.get("title"))
    print("-" * 50)
    print(detail.get("content"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
