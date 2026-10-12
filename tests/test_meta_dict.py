from rag.meta_dict import build


def doc(committee, questioners=(), answerers=()):
    return {"committee_name": committee, "meeting_name": "본회의",
            "questioners": list(questioners), "answerers": list(answerers)}


def person(name, position="", affiliation=""):
    return {"name": name, "position": position, "affiliation": affiliation}


def test_counts_documents_per_value():
    docs = [
        # 같은 문서에서 두 번 나온 이름은 한 번만 센다
        doc("교육위원회", [person("김갑", "위원")],
            [person("김갑", "위원"), person("박병", "장관", "교육부")]),
        doc("교육위원회", [person("김갑", "위원")]),
        doc("", answerers=[person("", "차관")]),
    ]

    result = build(docs)

    assert result["committee_name"] == {"교육위원회": 2}
    assert result["meeting_name"] == {"본회의": 3}
    assert result["name"] == {"김갑": 2, "박병": 1}
    assert result["position"] == {"위원": 2, "장관": 1, "차관": 1}
    assert result["affiliation"] == {"교육부": 1}
