from vectra.knowledge_base import ingest_decision, load_articles


def test_only_current_reviewed_articles_are_ingested():
    decisions = {a.doc_id: ingest_decision(a) for a in load_articles()}
    assert len(decisions) == 9
    assert [d for d, (ok, _) in decisions.items() if not ok] == ["KB-002", "KB-099"]
    assert "superseded by KB-007" in decisions["KB-002"][1]
    assert "prompt injection" in decisions["KB-099"][1]


def test_tables_stay_whole():
    docs = {a.doc_id: a.text for a in load_articles()}
    for row in ("| P1 |", "| P2 |", "| P3 |", "| P4 |", "VIP rule"):
        assert row in docs["KB-003"]
    for row in ("ZT-401", "ZT-503", "Negotiating", "WMS will not open"):
        assert row in docs["KB-007"]
