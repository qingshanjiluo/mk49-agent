"""Fetch the last few comments the agent just posted, to eyeball quality."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    for pid in (481899, 481900, 481901):
        for tid in (48690, 48687, 48686):
            try:
                comments = agent.client.all_comments(tid)
            except Exception:
                continue
            for c in comments:
                if c.get("id") == pid:
                    u = (c.get("user") or {})
                    print("--- post %s in thread %s (by %s) ---"
                          % (pid, tid, u.get("nickname")))
                    print(c.get("content"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
