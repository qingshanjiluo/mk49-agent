"""Memory toolkit: notes store with write/read/search/link/groom."""
import re
import time

from .base import Tool, schema, jdump


def _notes(agent):
    return agent.state.data.setdefault("notes", [])


class MemWrite(Tool):
    name = "mem_write"
    description = ("Write a durable note into long-term memory (facts about "
                   "members, forum lore, lessons learned, plans).")
    params = schema({"text": ("string", "note content, concise Chinese"),
                     "tags": ("array", "tags like [user, rule, game]"),
                     "links": ("array", "related note ids")},
                    required=["text"])

    def run(self, agent, text="", tags=None, links=None):
        notes = _notes(agent)
        nid = "n%d" % int(time.time() * 1000 % 1e9)
        notes.append({"id": nid, "ts": time.time(),
                      "text": text.strip()[:500],
                      "tags": [str(t)[:16] for t in (tags or [])[:5]],
                      "links": [str(l) for l in (links or [])[:6]]})
        if len(notes) > 400:
            del notes[: len(notes) - 400]
        return "saved %s" % nid


class MemRead(Tool):
    name = "mem_read"
    description = "Read recent notes (optionally filtered by tag)."
    params = schema({"tag": ("string", "filter by tag"),
                     "limit": ("integer", "default 10")}, required=[])

    def run(self, agent, tag=None, limit=10):
        notes = _notes(agent)
        if tag:
            notes = [n for n in notes if tag in n.get("tags", [])]
        return jdump([{"id": n["id"], "tags": n["tags"],
                       "text": n["text"]} for n in notes[-limit:]])


class MemSearch(Tool):
    name = "mem_search"
    description = "Keyword search over all memory notes."
    params = schema({"query": ("string", "keywords")}, required=["query"])

    def run(self, agent, query=""):
        hits = [n for n in _notes(agent)
                if query.lower() in (n.get("text", "") + " "
                                     + " ".join(n.get("tags", []))).lower()]
        return jdump([{"id": n["id"], "text": n["text"]}
                      for n in hits[-12:]])


class MemLink(Tool):
    name = "mem_link"
    description = "Link two notes (bidirectional relation)."
    params = schema({"id_a": ("string", "note id"),
                     "id_b": ("string", "note id")}, required=["id_a", "id_b"])

    def run(self, agent, id_a="", id_b=""):
        for n in _notes(agent):
            if n["id"] == id_a and id_b not in n["links"]:
                n["links"].append(id_b)
            if n["id"] == id_b and id_a not in n["links"]:
                n["links"].append(id_a)
        return "linked %s <-> %s" % (id_a, id_b)


class MemGroom(Tool):
    name = "mem_groom"
    description = ("Tidy memory: drop exact-duplicate notes, drop notes older "
                   "than N days without tags. Returns how many removed.")
    params = schema({"keep_days": ("integer", "drop untagged older than this, "
                                            "default 30")}, required=[])

    def run(self, agent, keep_days=30):
        notes = _notes(agent)
        seen, kept = set(), []
        cutoff = time.time() - keep_days * 86400
        for n in notes:
            key = re.sub(r"\s+", " ", n.get("text", "")).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            if not n.get("tags") and n.get("ts", 0) < cutoff:
                continue
            kept.append(n)
        removed = len(notes) - len(kept)
        agent.state.data["notes"] = kept
        return "groomed: %d removed, %d kept" % (removed, len(kept))


def register_all(reg):
    for t in (MemWrite(), MemRead(), MemSearch(), MemLink(), MemGroom()):
        reg.register(t)
