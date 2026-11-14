"""Basic toolkit: shell, files, context distillation, skills."""
import os
import re
import subprocess

from .base import Tool, schema

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS_DIR = os.path.join(REPO, "skills")

SAFE_PATH = re.compile(r"[\w\-./\\ \u4e00-\u9fff]+")


def _safe_path(path):
    path = os.path.abspath(os.path.join(REPO, path))
    if not path.startswith(REPO):
        raise ValueError("path outside workspace")
    return path


class ShellExec(Tool):
    name = "shell_exec"
    description = ("Run a shell command in the workspace (PowerShell on this "
                   "host). 30s timeout, output truncated. Read-only work "
                   "preferred; do not kill the agent's own process.")
    params = schema({"command": ("string", "command line to run")},
                    required=["command"])
    max_result = 3000

    def run(self, agent, command=""):
        r = subprocess.run(command, shell=True, capture_output=True,
                           text=True, timeout=30, cwd=REPO,
                           errors="replace")
        out = (r.stdout or "") + ("\n[stderr] " + r.stderr if r.stderr else "")
        return "exit=%d\n%s" % (r.returncode, out.strip()[:2800])


class FileRead(Tool):
    name = "file_read"
    description = "Read a text file inside the workspace (relative path)."
    params = schema({"path": ("string", "relative or absolute path")},
                    required=["path"])
    max_result = 3000

    def run(self, agent, path=""):
        with open(_safe_path(path), "r", encoding="utf-8",
                  errors="replace") as fh:
            return fh.read()


class FileWrite(Tool):
    name = "file_write"
    description = "Create or overwrite a text file inside the workspace."
    params = schema({"path": ("string", "file path"),
                     "content": ("string", "full file content")},
                    required=["path", "content"])

    def run(self, agent, path="", content=""):
        p = _safe_path(path)
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        return "written %d bytes to %s" % (len(content.encode("utf-8")), path)


class FileEdit(Tool):
    name = "file_edit"
    description = "Replace an exact old snippet with new text in a file."
    params = schema({"path": ("string", "file path"),
                     "old": ("string", "exact text to find"),
                     "new": ("string", "replacement text")},
                    required=["path", "old", "new"])

    def run(self, agent, path="", old="", new=""):
        p = _safe_path(path)
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            s = fh.read()
        if old not in s:
            return "ERROR: old text not found"
        s = s.replace(old, new, 1)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(s)
        return "edited %s" % path


class ContextDistill(Tool):
    name = "context_distill"
    description = ("Compress long text into a compact summary (keeps facts, "
                   "drops filler). Use before storing big findings.")
    params = schema({"text": ("string", "text to distill"),
                     "max_chars": ("integer", "target length, default 400")},
                    required=["text"])

    def run(self, agent, text="", max_chars=400):
        out = agent.llm.text(
            "Distill the following into at most %d characters. Keep concrete "
            "facts (names/numbers/rules), drop filler. Output only the "
            "distilled Chinese text.\n%s" % (max_chars, text[:4000]),
            tier="fast", max_tokens=400, temperature=0.2)
        return out


class SkillRead(Tool):
    name = "skill_read"
    description = ("Read an agent skill file (skills/<name>.txt). Skills are "
                   "persistent how-to knowledge the agent wrote for itself.")
    params = schema({"name": ("string", "skill name without extension")},
                    required=["name"])

    def run(self, agent, name=""):
        name = re.sub(r"[^\w\-]", "", name)
        p = os.path.join(SKILLS_DIR, name + ".txt")
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()


class SkillWrite(Tool):
    name = "skill_write"
    description = ("Write/overwrite a skill file (skills/<name>.txt) so "
                   "future sessions load this how-to into the system prompt.")
    params = schema({"name": ("string", "skill name (word chars only)"),
                     "content": ("string", "skill body, Chinese, concise")},
                    required=["name", "content"])

    def run(self, agent, name="", content=""):
        name = re.sub(r"[^\w\-]", "", name)[:40]
        if not name:
            return "ERROR: bad skill name"
        os.makedirs(SKILLS_DIR, exist_ok=True)
        with open(os.path.join(SKILLS_DIR, name + ".txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(content.strip() + "\n")
        agent.refresh_skills()
        return "skill saved: %s (%d chars)" % (name, len(content))


def register_all(reg):
    for t in (ShellExec(), FileRead(), FileWrite(), FileEdit(),
              ContextDistill(), SkillRead(), SkillWrite()):
        reg.register(t)
