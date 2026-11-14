"""Automation toolkit: sleep, scheduled scripts (send later, self-messages)."""
import time

from .base import Tool, schema, jdump


class Sleep(Tool):
    name = "sleep"
    description = ("Sleep inside the agent loop (human pacing). Max 240s per "
                   "call; for longer waits use schedule_task instead.")
    params = schema({"seconds": ("integer", "1-240")}, required=[])

    def run(self, agent, seconds=30):
        seconds = max(1, min(int(seconds or 30), 240))
        time.sleep(seconds)
        return "slept %ss" % seconds


class ScheduleTask(Tool):
    name = "schedule_task"
    description = ("Schedule a future automation script. The script is a "
                   "list of tool calls executed when due (e.g. post a thread "
                   "tomorrow noon, or send a message to myself later).")
    params = schema({
        "note": ("string", "what this task is for"),
        "delay_seconds": ("integer", "run after N seconds (or use run_at)"),
        "run_at": ("string", "absolute time 'YYYY-MM-DD HH:MM' local"),
        "script": ("array", "steps: [{\"tool\": name, \"args\": {...}}, ...]"),
    }, required=["note", "script"])
    danger = False   # queued; danger re-checked at execution time

    def run(self, agent, note="", delay_seconds=None, run_at=None,
            script=None):
        if not isinstance(script, list) or not script:
            return "ERROR: script must be a non-empty step list"
        run_at_ts = None
        if run_at:
            from datetime import datetime
            try:
                run_at_ts = datetime.strptime(str(run_at),
                                              "%Y-%m-%d %H:%M").timestamp()
            except ValueError:
                return "ERROR: run_at format YYYY-MM-DD HH:MM"
        if run_at_ts is None:
            try:
                run_at_ts = time.time() + max(60, int(delay_seconds or 600))
            except (TypeError, ValueError):
                run_at_ts = time.time() + 600
        item = agent.workflow.enqueue(
            "script_runner", run_at=run_at_ts,
            payload={"script": script[:12]}, note=note[:80])
        return jdump({"queued": True, "due_in_s":
                      int(item["run_at"] - time.time()), "note": note[:80]})


class ListScheduled(Tool):
    name = "list_scheduled"
    description = "List my pending scheduled automation tasks."
    params = schema({}, required=[])

    def run(self, agent):
        now = time.time()
        rows = [{"note": it.get("note"), "due_in_s": int(it["run_at"] - now),
                 "steps": len((it.get("payload") or {}).get("script", []))}
                for it in agent.workflow.due()]
        return jdump(rows)


class CancelScheduled(Tool):
    name = "cancel_scheduled"
    description = "Cancel one pending scheduled task by its note text."
    params = schema({"note": ("string", "note of the task to cancel")},
                    required=["note"])

    def run(self, agent, note=""):
        q = agent.state.data.get("workflow_queue", [])
        before = len(q)
        agent.state.data["workflow_queue"] = [
            it for it in q if it.get("note") != note]
        return "cancelled %d task(s)" % (before - len(
            agent.state.data["workflow_queue"]))


def register_all(reg):
    for t in (Sleep(), ScheduleTask(), ListScheduled(), CancelScheduled()):
        reg.register(t)
