"""Register an evening full-cycle task (learn + interactions, digest no-op)."""
import subprocess

CWD = r"G:\皮皮\编程项目\admin_bot"
TASK = "mk49-evening-cycle"
CMD = 'cmd /c cd /d "%s" && python run.py run >> state\\cycle_task.log 2>&1' % CWD

subprocess.run(
    ["schtasks", "/Create", "/F", "/TN", TASK,
     "/TR", CMD, "/SC", "DAILY", "/ST", "20:30"],
    check=False,
)
out = subprocess.run(["schtasks", "/Query", "/TN", TASK],
                     capture_output=True, text=True)
print(out.stdout[-600:] or out.stderr[-300:])
