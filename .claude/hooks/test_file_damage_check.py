import subprocess

import pytest
from file_damage_check import changed_files, problems, triggered


@pytest.mark.parametrize(("command", "args", "expected"), [
    ("cat > a.md <<'EOF'\n내용\nEOF", [], False),
    ("uv run python - <<'EOF'\nopen('a.py', 'w')\nEOF", [], True),
    ("sed -i 's/a/b/' docs/PLAN.md", ["sed"], True),
    ("git status --short", [], False),
    ("uv run pytest -q", [], False),
    # python과 sed -i가 함께 든 명령은 python 핸들러만 본다(알림 두 번 실측)
    ("sed -i 's/a/b/' f && uv run python x.py", ["sed"], False),
    ("sed -i 's/a/b/' f && uv run python x.py", [], True),
])
def test_triggered(command, args, expected):
    assert triggered(command, args) is expected


def test_reports_broken_python_and_crlf(tmp_path):
    # S17: 문자열 안 "\n"이 실제 줄바꿈으로 들어간 테스트 파일
    (tmp_path / "broken.py").write_text('x = "a\nb"\n', encoding="utf-8", newline="\n")
    (tmp_path / "crlf.py").write_bytes(b"x = 1\r\ny = 2\r\n")  # S16: write_text가 CRLF로 씀
    found = problems(["broken.py", "crlf.py"], tmp_path)
    assert len(found) == 2
    assert found[0].startswith("broken.py:1: 파이썬 구문 오류")
    assert found[1].startswith("crlf.py: 줄바꿈에 CRLF")


def test_normal_escapes_and_binary_pass(tmp_path):
    (tmp_path / "ok.py").write_text('rows = "\\n".join(["a", "b"]) + "\\n"\n', encoding="utf-8",
                                    newline="\n")
    (tmp_path / "doc.md").write_text("범위 1\\~2분\n", encoding="utf-8", newline="\n")
    (tmp_path / "emb.npy").write_bytes(b"\x93NUMPY\0\r\n")
    assert problems(["ok.py", "doc.md", "emb.npy", "missing.py"], tmp_path) == []


def test_changed_files_lists_modified_new_and_renamed_not_deleted(tmp_path):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    for name in ["keep.py", "gone.py", "old_name.py"]:
        (tmp_path / name).write_text(f"x = '{name}'\n", encoding="utf-8")
    git("add", ".")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "chore: 시작")
    (tmp_path / "keep.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "gone.py").unlink()
    git("mv", "old_name.py", "new_name.py")  # 스테이징된 이름 변경: 옛 경로가 따로 온다
    (tmp_path / "new dir").mkdir()
    (tmp_path / "new dir" / "a.py").write_text("y = 1\n", encoding="utf-8")
    assert sorted(changed_files(tmp_path)) == ["keep.py", "new dir/a.py", "new_name.py"]
