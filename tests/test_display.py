"""회의 정보 괄호 표시(S45). 합성 답변으로 본다."""

import pytest

from rag.display import MeetingInfoMover, move_meeting_info

MAX_NAME = 40
HEAD = "2018년 10월 10일 국방위원회"
PAREN = "(2018년 10월 10일 국방위원회)"


def fed(parts) -> str:
    mover = MeetingInfoMover(MAX_NAME)
    return "".join(mover.feed(p) for p in parts) + mover.finish()


CASES = [
    # 옮기는 문장
    (f"{HEAD} 회의에서 A는 답했습니다 [1].", f"A는 답했습니다{PAREN} [1]."),
    (f"{HEAD}에서 A는 답했습니다 [1].", f"A는 답했습니다{PAREN} [1]."),
    (f"{HEAD} 회의에서는 A는 답했습니다 [1].", f"A는 답했습니다{PAREN} [1]."),
    (f"{HEAD} 회의에서, A는 답했습니다 [1].", f"A는 답했습니다{PAREN} [1]."),
    (f"{HEAD} 회의에서는, A는 답했습니다 [1].", f"A는 답했습니다{PAREN} [1]."),
    # 인용 번호나 마침표 중 먼저 나오는 곳
    (f"{HEAD} 회의에서 A는 찬성했으며 [1], B는 반대했습니다 [2].",
     f"A는 찬성했으며{PAREN} [1], B는 반대했습니다 [2]."),
    # 문장 시작: 앞 문장의 끝 뒤, 문단 처음
    (f"앞 문장입니다 [1]. {HEAD} 회의에서 A는 답했습니다 [2].",
     f"앞 문장입니다 [1]. A는 답했습니다{PAREN} [2]."),
    (f"앞 문장입니다. [1] {HEAD} 회의에서 A는 답했습니다 [2].",
     f"앞 문장입니다. [1] A는 답했습니다{PAREN} [2]."),
    (f"앞 문단\n\n{HEAD} 회의에서 A는 답했습니다 [2].", f"앞 문단\n\nA는 답했습니다{PAREN} [2]."),
    # 숫자 사이의 점은 문장 끝이 아니다
    (f"{HEAD} 회의에서 A는 63.9%라고 답했습니다 [1].", f"A는 63.9%라고 답했습니다{PAREN} [1]."),
    ("비율은 63.2018년 10월 10일 회의에서 나왔다.", "비율은 63.2018년 10월 10일 회의에서 나왔다."),
    # 인용 없는 문장, 끝나지 않은 문장, 문단이 끝나는 문장
    (f"{HEAD} 회의에서 A는 답했습니다.", f"A는 답했습니다{PAREN}."),
    (f"{HEAD} 회의에서 A는 답하", f"A는 답하{PAREN}"),
    (f"{HEAD} 회의에서 A는 답하 ", f"A는 답하{PAREN} "),
    (f"{HEAD} 회의에서 A는 답함\n\n다음", f"A는 답함{PAREN}\n\n다음"),
    (f"{HEAD} 회의에서 A는 [참고] 답함 [1].", f"A는 [참고] 답함{PAREN} [1]."),
    # 패턴에 안 맞는 문장은 그대로
    ("2021년 국정감사에서 A는 답했습니다 [1].", "2021년 국정감사에서 A는 답했습니다 [1]."),
    ("2018년 10월 10일, 국방위원회에서 A는 답함.", "2018년 10월 10일, 국방위원회에서 A는 답함."),
    ("2018년 10월 10일 A는 답했습니다 [1].", "2018년 10월 10일 A는 답했습니다 [1]."),
    (f"{HEAD} 회의에서의 논의입니다 [1].", f"{HEAD} 회의에서의 논의입니다 [1]."),
    (f"문장 가운데 {HEAD} 회의에서 A는 답함 [1].", f"문장 가운데 {HEAD} 회의에서 A는 답함 [1]."),
    (f"2018년 10월 10일 {'가' * (MAX_NAME + 1)} 회의에서 A는 답함 [1].",
     f"2018년 10월 10일 {'가' * (MAX_NAME + 1)} 회의에서 A는 답함 [1]."),
    # 잘린 첫머리와 첫머리 뒤에 본문이 없는 답변
    ("2018", "2018"),
    ("2018년 10월 10일 국방", "2018년 10월 10일 국방"),
    (f"{HEAD} 회의에서", f"{HEAD} 회의에서"),
    (f"{HEAD} 회의에서 ", f"{HEAD} 회의에서 "),
    (f"{HEAD} 회의에서 [1].", f"{HEAD} 회의에서 [1]."),
    (f"{HEAD} 회의에서 \n\n다음", f"{HEAD} 회의에서 \n\n다음"),
    ("", ""),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_move_gives_same_text_however_pieces_are_split(raw, expected):
    assert move_meeting_info(raw, MAX_NAME) == expected
    assert fed(raw) == expected  # 한 글자씩
    for cut in range(len(raw) + 1):
        assert fed([raw[:cut], raw[cut:]]) == expected


def test_body_is_released_while_it_arrives():
    """본문을 문장 끝까지 잡아 두지 않는다(D-86 결정 3)."""
    mover = MeetingInfoMover(MAX_NAME)
    assert mover.feed(f"{HEAD} 회의에") == ""
    assert mover.feed("서 A는 답") == "A는 답"
    assert mover.feed("했습니다") == "했습니다"
    assert mover.feed(" [1") == f"{PAREN} [1"
