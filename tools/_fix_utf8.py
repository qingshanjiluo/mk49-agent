"""Force UTF-8 console at startup (GBK console crashes on rare unicode)."""
import io

P = "run.py"
s = io.open(P, encoding="utf-8").read()

old = "def main(argv):"
new = """def _force_utf8_console():
    \"\"\"GBK console chokes on exotic unicode in nicknames.\"\"\"
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main(argv):
    _force_utf8_console()"""
assert old in s, "main anchor"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("utf8 console forced")
