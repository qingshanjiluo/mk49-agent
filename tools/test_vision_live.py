"""Live test: extract + vision-describe images from a real image-heavy
thread (uses the earlier observed '新战舰@kr' thread 48877 with an inline
image, falls back to scanning recent threads for any with images)."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent
from mk49.tools.vision import extract_thread_images


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    # find a thread with images
    cands = [48877, 48552]
    threads, _ = agent.client.list_threads(page_limit=10)
    cands += [t["id"] for t in threads]
    picked = None
    for tid in cands:
        try:
            d = agent.client.thread_detail(tid) or {}
        except Exception:
            continue
        html = d.get("content") or ""
        urls = extract_thread_images(html, limit=4)
        if urls:
            picked = (tid, d, urls)
            break
    if not picked:
        print("no image thread found")
        return 1
    tid, detail, urls = picked
    print("thread", tid, "|", (detail.get("title") or "")[:40])
    print("images found:", len(urls))
    out = agent.registry.dispatch(agent, "forum_read_thread_images",
                                  {"thread_id": tid, "max_images": 2})
    print(out[:1500])
    agent.state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
