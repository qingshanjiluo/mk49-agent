"""Forum knowledge learner: reads tutorial/science/newbie categories, extracts
durable knowledge (game mechanics MK48/MK49, forum rules, tips, culture) and
format usage stats (cards / images / code) via the LLM, then persists a
knowledge base that gets injected into the agent's system prompt.
"""

import json
import os
import re
from datetime import date

from mbbs.content import strip_html, truncate

CARD_RE = re.compile(r"\[(?:threadcard|usercard):[1-9]\d*\]")
IMG_RE = re.compile(r"<img[^>]+src=", re.I)
CODE_RE = re.compile(r"(<pre|<code|```)", re.I)
POLL_RE = re.compile(r"mbbs-pol[l]:")
TABLE_RE = re.compile(r"<table|^\|.+\|$", re.I | re.M)

TAGS = ("game", "forum", "rule", "tip", "culture", "format")


class KnowledgeBase:
    def __init__(self, path):
        self.path = path
        self.data = {"items": [], "format_stats": {}, "updated": None}

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                self.data.update(saved)
        except (OSError, ValueError):
            pass
        return self

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def merge(self, items, max_items=120):
        """items: [{topic, fact, tags, source}] - dedupe by topic, cap size."""
        known = {it.get("topic") for it in self.data["items"]}
        added = 0
        for it in items:
            topic = (it.get("topic") or "").strip()[:60]
            fact = (it.get("fact") or "").strip()[:400]
            if not topic or not fact or topic in known:
                continue
            tags = [t for t in (it.get("tags") or []) if t in TAGS][:3]
            self.data["items"].append({
                "topic": topic,
                "fact": fact,
                "tags": tags or ["forum"],
                "source": it.get("source"),
                "day": date.today().isoformat(),
            })
            known.add(topic)
            added += 1
        if len(self.data["items"]) > max_items:
            self.data["items"] = self.data["items"][-max_items:]
        return added

    def add_format_stats(self, counters):
        for key, n in counters.items():
            self.data["format_stats"][key] = \
                self.data["format_stats"].get(key, 0) + int(n)

    def prompt_digest(self, limit=1400):
        """Compact text injected into the system prompt."""
        lines = []
        for it in self.data["items"][-40:]:
            lines.append("- [%s] %s: %s"
                         % ("/".join(it.get("tags", [])),
                            it.get("topic"), it.get("fact")))
        text = "\n".join(lines)
        return text[:limit] if text else ""

    def to_markdown(self):
        out = ["# Forum knowledge base",
               "",
               "Updated: %s | items: %d | format stats: %s"
               % (self.data.get("updated"), len(self.data["items"]),
                  json.dumps(self.data.get("format_stats", {}),
                             ensure_ascii=False)),
               ""]
        by_tag = {}
        for it in self.data["items"]:
            for t in it.get("tags", ["forum"]):
                by_tag.setdefault(t, []).append(it)
        names = {"game": "MK48/MK49 gameplay", "forum": "Forum info",
                 "rule": "Rules", "tip": "Tips",
                 "culture": "Culture/memes", "format": "Formatting"}
        for tag in TAGS:
            items = by_tag.get(tag)
            if not items:
                continue
            out.append("## %s" % names.get(tag, tag))
            out.append("")
            for it in items[-25:]:
                src = (" ([threadcard:%s])" % it["source"]) if it.get("source") else ""
                out.append("- **%s**: %s%s" % (it["topic"], it["fact"], src))
            out.append("")
        return "\n".join(out)


class Learner:
    def __init__(self, agent):
        self.agent = agent
        cfg = agent.cfg
        self.categories = cfg.get("learning_categories") or [16, 36, 32, 37, 2]
        self.per_category = int(cfg.get("learn_threads_per_category", 5))
        self.kb = KnowledgeBase(
            cfg.get("knowledge_file") or "state/knowledge.json").load()

    # ---------------- format study ----------------
    def scan_format(self, thread):
        """Count card/image/code/poll/table usage in a real post's content."""
        raw = thread.get("_body_html") or ""
        counters = {
            "cards": len(CARD_RE.findall(raw)),
            "images": len(IMG_RE.findall(raw)),
            "code": 1 if CODE_RE.search(raw) else 0,
            "polls": 1 if POLL_RE.search(raw) else 0,
            "tables": 1 if TABLE_RE.search(raw) else 0,
        }
        self.kb.add_format_stats(counters)
        return counters

    # ---------------- knowledge extraction ----------------
    def extract_from_thread(self, thread):
        body = truncate(thread.get("_detail") or "", 600)
        comments = [
            truncate(strip_html(c.get("content") or ""), 120)
            for c in (thread.get("_comments") or [])[:5]
        ]
        if len(body) < 30 and not comments:
            return []
        prompt = (
            "Read this forum thread from mk49.top (a Chinese MK48/MK49 fleet "
            "game community). Extract 0-3 durable knowledge items for a bot "
            "that must behave like a seasoned member. Output JSON only:\n"
            '{"items":[{"topic":"<=20 chars Chinese topic",'
            '"fact":"<=120 chars Chinese fact",'
            '"tags":["game|forum|rule|tip|culture"]}]}'
            "\nFocus on: game mechanics/ships/meta, forum rules & culture, "
            "practical tips. Skip chit-chat, emotions, one-off jokes.\n\n"
            "Thread meta: " + truncate(thread.get("title") or "", 60) + "\n"
            "Body: " + body + "\n"
            + ("Comments: " + " | ".join(comments) if comments else "")
        )
        try:
            data = self.agent.llm.json(prompt, tier="fast", max_tokens=400)
        except Exception as exc:
            self.agent.log("knowledge extract failed: %s" % exc)
            return []
        items = []
        for it in (data.get("items") or [])[:3]:
            if isinstance(it, dict) and it.get("topic") and it.get("fact"):
                it["source"] = thread.get("id")
                items.append(it)
        return items

    # ---------------- main pass ----------------
    def run(self, max_threads=25):
        agent = self.agent
        names = {}
        try:
            names = {c.get("id"): c.get("name")
                     for c in agent.client.categories()}
        except Exception:
            pass
        scanned = 0
        added = 0
        for cat in self.categories:
            try:
                threads, _ = agent.client.list_threads(
                    category_id=cat,
                    page_limit=self.per_category)
            except Exception as exc:
                agent.log("learn category %s failed: %s" % (cat, exc))
                continue
            for t in threads[:self.per_category]:
                if scanned >= max_threads:
                    break
                tid = t.get("id")
                if not tid:
                    continue
                try:
                    detail = agent.client.thread_detail(tid) or {}
                except Exception:
                    detail = {}
                raw_content = detail.get("content") or ""
                t["_body_html"] = raw_content
                t["_detail"] = strip_html(
                    raw_content or detail.get("content_for_indexes") or "")
                try:
                    t["_comments"] = agent.client.all_comments(tid)[:6]
                except Exception:
                    t["_comments"] = []
                self.scan_format(t)
                items = self.extract_from_thread(t)
                added += self.kb.merge(items, max_items=120)
                scanned += 1
                if scanned % 5 == 0:
                    agent.log("learned %d/%d threads..." % (scanned, max_threads))
        self.kb.data["updated"] = date.today().isoformat()
        self.kb.save()
        md_path = os.path.splitext(self.kb.path)[0] + ".md"
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(self.kb.to_markdown())
        agent.log("knowledge pass done: %d threads, +%d items (total %d)"
                  % (scanned, added, len(self.kb.data["items"])))
        return {"threads": scanned, "added": added,
                "total": len(self.kb.data["items"]), "md": md_path}
