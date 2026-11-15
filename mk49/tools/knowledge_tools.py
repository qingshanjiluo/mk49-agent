"""Knowledge-base tools: the agent adds/edits/deletes/searches its own
knowledge (state/knowledge.json), with stable K### ids, persisted json+md
and hot-reloaded into the system prompt."""
import os

from .base import Tool, schema, jdump
from mk49.knowledge import KnowledgeBase, TAGS


def _kb(agent):
    """Shared loader: reuse agent.kb when live, else load from config path."""
    cfg = agent.cfg or {}
    path = cfg.get("knowledge_file") or "state/knowledge.json"
    kb = getattr(agent, "kb", None)
    if kb is not None:
        return kb
    return KnowledgeBase(path).load()


def _sync(agent, kb, action, kid=""):
    """Persist + hot-reload + log."""
    md = kb.persist(agent)
    agent.state.log("knowledge", "%s %s -> %s" % (action, kid,
                                                  os.path.basename(md)))
    return md


class KbList(Tool):
    name = "kb_list"
    description = "List/search knowledge entries with K### ids (read first)."
    params = schema({"query": ("string", "keyword filter"),
                     "limit": ("integer", "max rows, default 15")},
                   required=[])
    max_result = 3000

    def run(self, agent, query=None, limit=15):
        kb = _kb(agent)
        items = kb.listing(query, int(limit or 15))
        rows = [{"kid": it.get("kid") or "-", "topic": it.get("topic"),
                 "fact": it.get("fact"), "tags": it.get("tags"),
                 "day": it.get("day"), "source": it.get("source")}
                for it in items]
        return "total=%d\n%s" % (len(kb.data["items"]), jdump(rows))


class KbAdd(Tool):
    name = "kb_add"
    description = "Add one knowledge entry (assigns K### id, persists)."
    params = schema({"topic": ("string", "<=60 chars summary"),
                     "fact": ("string", "<=400 chars fact"),
                     "tags": ("array", "tags: " + "/".join(TAGS)),
                     "source": ("integer", "source thread id")},
                    required=["topic", "fact"])
    danger = False

    def run(self, agent, topic="", fact="", tags=None, source=None):
        kb = _kb(agent)
        ok, res = kb.add(topic, fact, tags=tags, source=source)
        if not ok:
            return "ERROR: %s" % res
        _sync(agent, kb, "add", res)
        return "added %s: %s" % (res, topic[:50])


class KbEdit(Tool):
    name = "kb_edit"
    description = "Edit an existing knowledge entry by K### id."
    params = schema({"kid": ("string", "e.g. K007"),
                     "topic": ("string", "new topic (optional)"),
                     "fact": ("string", "new fact (optional)"),
                     "tags": ("array", "new tags (optional)")},
                    required=["kid"])
    danger = False

    def run(self, agent, kid="", topic=None, fact=None, tags=None):
        kb = _kb(agent)
        ok, res = kb.edit(kid, topic=topic, fact=fact, tags=tags)
        if not ok:
            return "ERROR: %s" % res
        _sync(agent, kb, "edit", kid)
        return "edited %s -> %s: %s" % (kid, res.get("topic"),
                                        res.get("fact", "")[:60])


class KbDelete(Tool):
    name = "kb_delete"
    description = "Delete a knowledge entry by K### id."
    params = schema({"kid": ("string", "e.g. K007")}, required=["kid"])
    danger = False

    def run(self, agent, kid=""):
        kb = _kb(agent)
        ok, res = kb.delete(kid)
        if not ok:
            return "ERROR: %s" % res
        _sync(agent, kb, "delete", kid)
        return "deleted %s: %s" % (kid, res.get("topic", "")[:50])


def register_all(reg):
    for t in (KbList(), KbAdd(), KbEdit(), KbDelete()):
        reg.register(t)
