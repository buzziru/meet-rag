import json

from nb_kernel import TB_LINES, error_tail, lint


def test_error_tail_strips_ansi_and_keeps_last_lines():
    tb = [f"\x1b[31mline {i}\x1b[0m" for i in range(40)]
    out = error_tail([{"output_type": "stream", "text": "x"},
                      {"output_type": "error", "traceback": tb}])
    lines = out.splitlines()
    assert len(lines) == TB_LINES
    assert lines[-1] == "line 39"
    assert "\x1b" not in out


def test_error_tail_without_error_output():
    assert "오류 출력이 없다" in error_tail([])


def test_lint_fixes_but_does_not_format_notebook(tmp_path):
    nb = {"cells": [{"cell_type": "code", "metadata": {}, "outputs": [], "execution_count": None,
                     "source": ["import sys\n", "import os\n", "x=[1,2]\n", "print(os, sys, x)"]}],
          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path = tmp_path / "a.ipynb"
    path.write_text(json.dumps(nb), encoding="utf-8")
    lint(path)
    src = "".join(json.loads(path.read_text(encoding="utf-8"))["cells"][0]["source"])
    assert src.index("import os") < src.index("import sys")  # isort(I001) 자동 수정
    assert "x=[1,2]" in src  # ruff format은 적용하지 않는다(ADR-0063)
