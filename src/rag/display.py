"""화면에 보여 줄 답변 글. 문장 첫머리의 회의 정보를 문장 끝 괄호로 옮긴다(S45, D-86).

생성 기록과 judge 입력은 이 변환 앞이라 바뀌지 않는다. 명세는 docs/slices/45-meeting-info.md.
"""

import re

DATE = re.compile(r"(\d{4}년 \d{1,2}월 \d{1,2}일) ")
# 글자가 더 오면 날짜가 될 수 있는 첫머리
PARTIAL_DATE = re.compile(r"\d{1,3}|\d{4}(?:년(?: (?:\d{1,2}(?:월(?: (?:\d{1,2}일?)?)?)?)?)?)?")
AFTER_NAME = re.compile(r"는?,? ")
PARTIAL_AFTER_NAME = re.compile(r"는?,?")
NOT_IN_NAME = re.compile(r"[.,\n\[\]]")
SENTENCE_LEAD = re.compile(r"(?:\s+|\[\d+\])+")
PARTIAL_CITATION = re.compile(r"\[\d*")
BOUNDARY = re.compile(r"[ \t]*(?:\[\d|\n)|\.")
PARTIAL_BOUNDARY = re.compile(r"[ \t]*\[?$")


class MeetingInfoMover:
    """답변 조각을 받아 보여 줄 글을 낸다. 문장 첫머리가 회의 정보일 수 있는 동안만 잡아 두고 본문은
    받는 대로 내보낸다. 조각을 어떻게 나눠도 결과가 같다."""

    def __init__(self, max_name: int):
        self.max_name = max_name
        self.held = ""
        self.at_start = True
        self.last = ""  # 마지막으로 내보낸 글자. 숫자 사이의 점을 가린다
        self.paren = ""  # 아직 붙이지 못한 괄호
        self.removed = ""  # 괄호로 옮기려고 지운 첫머리. 뒤에 본문이 없으면 되돌린다

    def feed(self, piece: str) -> str:
        self.held += piece
        return self._pump(final=False)

    def finish(self) -> str:
        return self._pump(final=True)

    def _pump(self, final: bool) -> str:
        out = []
        while self.held:
            text = (self._start if self.at_start else self._body)(final)
            if text is None:  # 글자가 더 와야 정할 수 있다
                break
            out.append(text)
        if final:
            out.append(self._close())
        return "".join(out)

    def _take(self, n: int) -> str:
        text, self.held = self.held[:n], self.held[n:]
        if text:
            self.last = text[-1]
        return text

    def _close(self) -> str:
        """괄호를 낸다. 첫머리 뒤에 본문이 없었으면 지운 글을 그대로 되돌린다."""
        text = self.removed or self.paren
        self.paren = self.removed = ""
        return text

    def _start(self, final: bool) -> str | None:
        """문장 시작. 공백과 인용 번호를 지나 회의 정보인지 본다."""
        lead = SENTENCE_LEAD.match(self.held)
        if lead:
            return self._take(lead.end())
        wait = not final
        if wait and PARTIAL_CITATION.fullmatch(self.held):
            return None
        date = DATE.match(self.held)
        if date:
            rest = self.held[date.end():]
            at = rest.find("에서")
            name = rest if at < 0 else rest[:at]
            if not NOT_IN_NAME.search(name) and len(name) <= self.max_name:
                if at < 0:
                    if wait:
                        return None
                else:
                    after = rest[at + len("에서"):]
                    tail = AFTER_NAME.match(after)
                    if tail and name:
                        return self._hold_paren(date, name, date.end() + at + 2 + tail.end())
                    if wait and name and PARTIAL_AFTER_NAME.fullmatch(after):
                        return None
        elif wait and PARTIAL_DATE.fullmatch(self.held):
            return None
        self.at_start = False
        return ""

    def _hold_paren(self, date: re.Match, name: str, end: int) -> str:
        self.removed = self.held[:end]
        self.paren = f"({date.group(1)} {name.removesuffix(' 회의')})"
        self.held = self.held[end:]
        self.at_start = False
        return ""

    def _body(self, final: bool) -> str | None:
        """본문. 인용 번호, 마침표, 줄바꿈 앞에 괄호를 붙이고 문장 끝을 찾는다."""
        found = BOUNDARY.search(self.held)
        if not found:
            cut = PARTIAL_BOUNDARY.search(self.held).start()
            if cut:
                self.removed = ""
                return self._take(cut)
            # 끝의 공백이나 [ 뿐이다. 답변이 끝나면 괄호를 그 앞에 붙인다
            return self._close() + self._take(len(self.held)) if final else None
        if found.start():
            self.removed = ""
            return self._take(found.start())
        if found.group() != ".":
            self.at_start = found.group().endswith("\n")
            return self._close() + self._take(found.end())
        if self.last.isdigit():
            after = self.held[1:2]
            if not after and not final:
                return None
            if after.isdigit():
                self.removed = ""
                return self._take(1)
        self.at_start = True
        return self._close() + self._take(1)


def move_meeting_info(answer: str, max_name: int) -> str:
    mover = MeetingInfoMover(max_name)
    return mover.feed(answer) + mover.finish()


def replace_words(text: str, pairs: dict[str, str]) -> str:
    """화면 글에서 바꿀 말을 바꾼다(S52). 생성 원문은 바꾸지 않는다."""
    for old, new in pairs.items():
        text = text.replace(old, new)
    return text


class WordReplacer:
    """조각으로 오는 화면 글에서 바꿀 말을 바꾼다(S52). 조각 끝이 바꿀 말의 앞부분일 수 있으면 그
    글자만 다음 조각까지 잡아 둔다. 조각을 어떻게 나눠도 결과가 같다."""

    def __init__(self, pairs: dict[str, str]):
        self.pairs = pairs
        self.held = ""

    def feed(self, piece: str) -> str:
        text = self.held + piece
        keep = max((n for old in self.pairs for n in range(1, len(old))
                    if text.endswith(old[:n])), default=0)
        self.held = text[len(text) - keep:]
        return replace_words(text[:len(text) - keep], self.pairs)
