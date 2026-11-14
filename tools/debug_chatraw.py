"""Reproduce the in-loop master failure synchronously with full traceback."""
import io
import sys
import pathlib
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    print("timeout attr:", agent.llm.timeout)
    agent.observe()
    try:
        msg = agent.llm.chat_raw(
            [{"role": "system", "content": agent.llm.system("test")},
             {"role": "user", "content": "call any tool"}],
            tier="smart", max_tokens=200, tools=agent.registry.schemas())
        print("OK content:", repr((msg.get("content") or "")[:80]))
        print("tool_calls:", len(msg.get("tool_calls") or []))
    except Exception as exc:
        traceback.print_exc()
        print("FAILED:", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
