"""Verify fit_for_forum + upload chain, then also apply to image_post."""
import io
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from run import build_agent
from mk49 import images as img


def main():
    agent, cfg, llm = build_agent()
    agent.bootstrap()
    raw, ext = img.generate("sunset over a pixel-art harbor with dragon boats")
    print("generated:", len(raw), "bytes")
    data, ext2 = img.fit_for_forum(raw)
    print("fitted:", len(data), "bytes as", ext2)
    url = img.upload_to_forum(agent.client, data, "fit_test.%s" % ext2)
    print("uploaded:", url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
