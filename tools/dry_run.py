"""Dry-run: observe -> digest -> LLM plan, WITHOUT any forum writes.

Verifies the new pipeline end to end:
  login, metadata-rich observation, replyable filters (pinned / veteran /
  own threads), digest rendering, planner JSON with reply_targets.
"""
import io
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent
from mk49.llm import LLMError


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    obs = agent.observe()

    print("=== observation summary ===")
    print("new_threads:", len(obs.new_threads),
          "| replyable:", len(obs.replyable),
          "| skipped:", len(obs.skipped),
          "| mentions:", len(obs.mention_hits),
          "| unread:", obs.unread)
    for t in obs.replyable[:6]:
        print("  REPLYABLE id=%s cat=%s author=%s(uid=%s) floors=%d"
              % (t.get("id"), t.get("category_id"),
                 (t.get("user") or {}).get("nickname"),
                 (t.get("user") or {}).get("id"),
                 len(t.get("_comments") or [])))
    for tid, why in list(obs.skipped.items())[:10]:
        print("  SKIP id=%s (%s)" % (tid, why))

    print("\n=== planner digest (truncated) ===")
    digest = agent._observation_digest()
    print(json.dumps(digest, ensure_ascii=False, indent=1)[:1600])

    print("\n=== LLM plan ===")
    try:
        plan = agent._llm_plan()
        print(json.dumps(plan, ensure_ascii=False, indent=1))
    except LLMError as exc:
        print("LLM plan error:", exc)
        plan = None
    if plan is None:
        print("falling back to heuristic plan:")
        print(json.dumps(agent._heuristic_plan(), ensure_ascii=False, indent=1))

    print("\nDRY RUN COMPLETE - no forum writes performed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
