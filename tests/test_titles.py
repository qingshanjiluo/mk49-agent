import sys, pathlib, io
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from mk49.llm import _clean_title


def test_prompt_echo_stripped():
    assert _clean_title('用户要求为论坛板块「聊天」想一个吸引人但正常的帖子标题，15字以内，不涉政，不标') == ""


def test_title_prefix_removed():
    assert _clean_title("标题：今天天气真好") == "今天天气真好"
    assert _clean_title("标题: 周末摸鱼指南") == "周末摸鱼指南"


def test_brackets_and_quotes_removed():
    assert _clean_title("《夜航》") == "夜航"
    assert _clean_title('"海风与灯塔"') == "海风与灯塔"


def test_plain_title_kept():
    assert _clean_title("海风与灯塔") == "海风与灯塔"


def test_truncated_at_sentence():
    assert _clean_title("夜航船。后面还有解释文字") == "夜航船"


def test_empty_input():
    assert _clean_title("") == ""
    assert _clean_title(None) == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); passed += 1
        except Exception:
            import traceback; traceback.print_exc(); print("FAIL", f.__name__)
    print("%d/%d title tests passed" % (passed, len(fns)))
    sys.exit(0 if passed == len(fns) else 1)
