from .base import Tool, ToolRegistry, schema, jdump  # noqa: F401
from . import basic, forum, image_tools, webtools, auto, memory_tools  # noqa: F401


def build_registry():
    reg = ToolRegistry()
    for mod in (basic, forum, image_tools, webtools, auto, memory_tools):
        mod.register_all(reg)
    return reg
