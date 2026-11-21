from .base import Tool, ToolRegistry, schema, jdump  # noqa: F401
from . import (basic, forum, image_tools, webtools, auto, memory_tools, vision, knowledge_tools, chat)  # noqa: F401


def build_registry():
    reg = ToolRegistry()
    for mod in (basic, forum, image_tools, webtools, auto, memory_tools, vision, knowledge_tools, chat):
        mod.register_all(reg)
    return reg
