"""Autonomous workflow queue: the agent schedules its own future work.

Tasks are plain dicts stored in state, each with a due time and a feature
name to run. One due task executes per cycle, keeping behaviour paced.
"""

import time


class Workflow:
    def __init__(self, state):
        self.state = state
        state.data.setdefault("workflow_queue", [])

    def enqueue(self, task, run_at=None, payload=None, note=""):
        """task: feature name; run_at: epoch seconds (default now+600)."""
        item = {
            "task": task,
            "run_at": run_at or (time.time() + 600),
            "payload": payload or {},
            "note": note,
            "queued_at": time.time(),
        }
        q = self.state.data["workflow_queue"]
        q.append(item)
        if len(q) > 60:
            del q[: len(q) - 60]
        return item

    def due(self, now=None):
        now = now or time.time()
        q = self.state.data["workflow_queue"]
        ready = [it for it in q if it.get("run_at", 0) <= now]
        ready.sort(key=lambda it: it.get("run_at", 0))
        return ready

    def pop(self):
        q = self.state.data["workflow_queue"]
        ready = self.due()
        if not ready:
            return None
        item = ready[0]
        q.remove(item)
        return item

    def execute_one(self, agent, now=None):
        """Run at most one due task; returns (task_name, result|None)."""
        item = self.pop()
        if not item:
            return None, None
        task = item["task"]
        feat = agent.features.get(task)
        if feat is None:
            agent.log("workflow: unknown task %s" % task)
            return task, None
        agent.log("workflow run: %s (%s)" % (task, item.get("note", "")))
        try:
            plan = dict(item.get("payload") or {})
            plan[task] = True
            result = feat.run(agent, plan)
        except Exception as exc:
            agent.log("workflow task %s failed: %s" % (task, exc))
            result = None
        agent.state.log("workflow", "%s=%s" % (task, result))
        return task, result
