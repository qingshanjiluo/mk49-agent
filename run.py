"""Entry point.

  python run.py run            # one autonomous cycle
  python run.py loop            # continuous cycles (scan_interval)
  python run.py digest         # force daily digest post
  python run.py doctor         # connectivity + capability report
  python run.py demo-image "a cat astronaut"   # generate+upload image
"""

import sys
import traceback

from features import load_all
from mbbs.client import MBBSClient
from mk49.agent import Agent
from mk49.config import load_config
from mk49.llm import ChatClient
from mk49.state import State


def build_agent():
    cfg = load_config()
    client = MBBSClient(cfg["base_url"], cfg.get("username", ""),
                        cfg.get("password", ""))
    state = State(cfg["state_file"])
    features = load_all()
    try:
        llm = ChatClient()
    except Exception as exc:
        print("[boot] LLM unavailable (%s), heuristic decisions only" % exc)
        llm = None
    agent = Agent(client, llm, state, cfg, features)
    return agent, cfg, llm


def cmd_doctor():
    agent, cfg, llm = build_agent()
    print("=" * 60)
    print("base_url     :", cfg["base_url"])
    print("username     :", cfg["username"] or "(not set)")
    print("LLM channels :", len(llm.channels) if llm else 0)
    if llm:
        for base, _key, model in llm.channels:
            print("   -", model, "@", base)
    print("=" * 60)
    if not agent.client.ensure_login():
        print("[doctor] LOGIN FAILED")
        return 1
    me = agent.client.me() or {}
    gid = (me.get("group") or {}).get("id")
    perms = agent.client.user_permissions(gid)
    print("login OK  -> %s (group=%s)" % (me.get("nickname"), (me.get("group") or {}).get("name")))
    cats = agent.client.categories()
    print("categories : %d" % len(cats))
    can_post = [c.get("id") for c in cats
                if "category%s.createThread" % c.get("id") in perms]
    print("can post in categories:", can_post)
    print("can reply/like/upload/vote:",
          "thread.reply" in perms, "thread.like" in perms,
          any(p.startswith("attachment.create") for p in perms),
          "thread.votePoll" in perms)
    print("unread messages:", agent.client.unread_count())
    threads, total = agent.client.list_threads(page_limit=3)
    print("threads visible: %d (total=%s)" % (len(threads), total))
    tags = agent.client.all_tags()
    print("tags:", [t.get("name") for t in tags])
    emojis = agent.client.emojis()
    print("emojis: %d" % len(emojis))
    print("[doctor] ALL GREEN" if threads and can_post else "[doctor] CHECK ISSUES")
    return 0


def cmd_demo_image(prompt="a cute cat astronaut, digital art"):
    agent, cfg, llm = build_agent()
    if not agent.client.ensure_login():
        print("login failed")
        return 1
    from mk49 import images as img
    raw, ext = img.generate(prompt, provider=cfg.get("image_provider"))
    print("generated %d bytes (%s)" % (len(raw), ext))
    url = img.upload_to_forum(agent.client, raw, "demo_%d.%s" % (int(__import__("time").time()), ext))
    print("uploaded ->", url)
    return 0


def cmd_digest():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    agent.observe()
    feat = agent.features.get("daily_digest")
    n = feat.run(agent, {"daily_digest": True})
    agent.state.save()
    print("digest posted:", n)
    return 0


def cmd_run():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    ran = agent.run_cycle()
    print("ran:", ran)
    return 0


def cmd_learn():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    feat = agent.features.get("knowledge_learner")
    n = feat.run(agent, {"learn": True})
    agent.state.save()
    print("learn done:", n)
    return 0


def cmd_loop():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    agent.run_forever()
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    table = {
        "run": cmd_run,
        "loop": cmd_loop,
        "doctor": cmd_doctor,
        "digest": cmd_digest,
        "learn": cmd_learn,
        "demo-image": cmd_demo_image,
    }
    fn = table.get(cmd)
    if not fn:
        print(__doc__)
        return 2
    try:
        if cmd == "demo-image":
            prompt = argv[2] if len(argv) > 2 else "a cute cat astronaut"
            return fn(prompt)
        return fn()
    except KeyboardInterrupt:
        print("bye")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
