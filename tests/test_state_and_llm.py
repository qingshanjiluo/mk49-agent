import sys, pathlib, io, os, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from mk49.state import State
from mk49.llm import extract_json

def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        st = State(p)
        st.mark_thread(123)
        st.mark_post(456)
        st.bump_daily("comments")
        st.bump_daily("comments")
        st.log("comment", "x")
        st.stat_bump("threads")
        st.save()
        st2 = State(p)
        assert st2.seen_thread(123) and st2.seen_post(456)
        assert st2.daily_count("comments") == 2
        assert st2.data["stats"]["threads"] == 1
        assert st2.recent_actions(10, "comment")

def test_state_capacity_trim():
    with tempfile.TemporaryDirectory() as d:
        st = State(os.path.join(d, "s.json"))
        for i in range(9000):
            st.mark_thread(i)
        assert len(st.data["processed_threads"]) <= 8000

def test_extract_json_variants():
    assert extract_json('{"a":1}') == {"a": 1}
    assert extract_json('```json\n{"a":2}\n```') == {"a": 2}
    assert extract_json('junk {"b":3} tail') == {"b": 3}
    assert extract_json("") == {}
    assert extract_json("not json") == {}

def test_daily_bucket_rollover():
    with tempfile.TemporaryDirectory() as d:
        st = State(os.path.join(d, "s.json"))
        st.bump_daily("threads")
        # simulate old day data
        st.data["daily"] = {"2000-01-01": {"threads": 5}}
        assert st.daily_count("threads") == 0  # old days pruned

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); passed += 1
        except Exception:
            import traceback; traceback.print_exc(); print("FAIL", f.__name__)
    print("%d/%d state/llm tests passed" % (passed, len(fns)))
    sys.exit(0 if passed == len(fns) else 1)
