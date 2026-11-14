"""Tool base class and registry for the mk49 agent."""
import difflib
import json
import traceback


class Tool:
    """A callable tool with JSON-schema parameters."""

    name = "tool"
    description = ""
    params = {"type": "object", "properties": {}, "required": []}
    danger = False          # True = forum write (blocked in quiet hours)
    max_result = 2400       # result chars kept for LLM context

    def run(self, agent, **kwargs):
        raise NotImplementedError

    def schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.params,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        self._tools[tool.name] = tool
        return tool

    def get(self, name):
        return self._tools.get(name)

    def names(self):
        return sorted(self._tools)

    def schemas(self):
        return [t.schema() for t in self._tools.values()]

    def resolve(self, name):
        """Exact hit, else closest tool name (LLMs sometimes guess)."""
        if name in self._tools:
            return self._tools[name]
        matches = difflib.get_close_matches(name, self._tools, n=1, cutoff=0.75)
        return self._tools[matches[0]] if matches else None

    def dispatch(self, agent, name, args):
        """Execute a tool; returns a text result (never raises)."""
        tool = self.resolve(name)
        if tool is None:
            return "ERROR: unknown tool %s" % name
        if tool.name != name:
            agent.log("tool alias: %s -> %s" % (name, tool.name))
        if tool.danger and agent.is_quiet_now():
            return "ERROR: quiet hours (23:00-08:00) - forum writes disabled"
        try:
            args = args or {}
            result = tool.run(agent, **args)
        except TypeError as exc:
            result = "ERROR: bad arguments: %s" % exc
        except Exception as exc:
            result = "ERROR: %s" % str(exc)[:300]
            traceback.print_exc()
        result = str(result)
        if len(result) > tool.max_result:
            result = result[: tool.max_result] + "\n...(truncated)"
        agent.state.log("tool", "%s ok=%s" % (name, not result.startswith("ERROR")))
        return result

    def help_text(self):
        rows = []
        for name in self.names():
            t = self._tools[name]
            rows.append("- %s%s: %s" % (name, " [write]" if t.danger else "",
                                        t.description))
        return "\n".join(rows)


def schema(props, required=None):
    """Compact JSON-schema builder: props = {name: (type, desc)}."""
    out = {"type": "object", "properties": {}}
    for k, (typ, desc) in props.items():
        out["properties"][k] = {"type": typ, "description": desc}
    if required:
        out["required"] = list(required)
    return out


def jdump(obj):
    return json.dumps(obj, ensure_ascii=False)
