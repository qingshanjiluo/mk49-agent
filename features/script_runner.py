"""Hidden feature: execute a scheduled automation script (tool-call list)."""

from . import Feature, register

MAX_STEPS = 12


@register
class ScriptRunner(Feature):
    name = "script_runner"
    desc = "Execute a scheduled automation script (list of tool calls)"
    plan_keys = ("script_runner",)

    def triggered_by(self, plan, agent):
        return bool(plan.get("script"))

    def run(self, agent, plan):
        script = plan.get("script") or []
        reg = getattr(agent, "registry", None)
        if reg is None:
            from mk49.tools import build_registry
            reg = build_registry()
        results = []
        for step in script[:MAX_STEPS]:
            if not isinstance(step, dict):
                continue
            tool = step.get("tool")
            args = step.get("args") or {}
            delay = step.get("delay")
            if delay:
                import time
                time.sleep(min(int(delay), 240))
            out = reg.dispatch(agent, tool, args)
            results.append("%s -> %s" % (tool, out[:120]))
            agent.log("script step %s: %s" % (tool, out[:80]))
        agent.state.log("script", "%d steps" % len(results))
        return 1
