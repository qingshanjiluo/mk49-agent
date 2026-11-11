"""Daily scheduled task setup for Windows Task Scheduler.

Registers a 09:05 daily task that publishes the forum digest, so the
"every day one digest" promise holds even when the agent is not in loop mode.
"""
import subprocess
import sys

CWD = r"G:\皮皮\编程项目\admin_bot"
TASK = "mk49-daily-digest"
CMD = 'cmd /c cd /d "%s" && python run.py digest >> state\\digest_task.log 2>&1' % CWD

subprocess.run(
    ["schtasks", "/Create", "/F", "/TN", TASK,
     "/TR", CMD, "/SC", "DAILY", "/ST", "09:05"],
    check=False,
)
out = subprocess.run(["schtasks", "/Query", "/TN", TASK],
                     capture_output=True, text=True)
print(out.stdout[-800:] or out.stderr[-400:])
