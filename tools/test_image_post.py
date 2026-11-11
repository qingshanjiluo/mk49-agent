"""End-to-end image post test: LLM topic -> furry gateway image gen ->
forum upload -> beautified markdown post, created then deleted."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    agent.observe()

    feat = agent.features["image_post"]
    plan = {"image_thread": True, "thread_category": 2, "thread_topic": ""}
    n = feat.run(agent, plan)
    print("image_post result:", n)

    # cleanup: delete the thread we just created
    mine, _ = agent.client.list_threads(user_id=agent.client.user_id, page_limit=1)
    if mine and mine[0].get("title"):
        tid = mine[0]["id"]
        print("deleting test thread:", tid, mine[0]["title"][:30])
        agent.client.delete_thread(tid)
        print("deleted")
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
