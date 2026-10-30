from vectra.agents import Draft, Hit, VerifierAgent
from vectra.safety import ABSTAIN_MESSAGE, find_unsafe

ZT_HITS = [Hit("KB-007", "ZenTunnel", 0.6, "...", "2026-04-01")]


def test_verifier_drops_citations_that_were_not_retrieved():
    v = VerifierAgent().run(Draft("Use zt-gw.vectralogistics.example.", ["KB-007", "KB-002"], False), ZT_HITS, None)
    assert v.citations == ["KB-007"] and v.checks["citations_dropped"] == ["KB-002"]


def test_verifier_abstains_when_nothing_valid_is_cited():
    v = VerifierAgent().run(Draft("Parking passes come from HR.", ["KB-123"], False), ZT_HITS, None)
    assert v.abstained and v.citations == [] and v.answer == ABSTAIN_MESSAGE


def test_verifier_blocks_unsafe_advice_and_stale_vpn():
    assert VerifierAgent().run(Draft("Turn off Windows Defender to speed it up.", ["KB-007"], False), ZT_HITS, None).abstained
    assert VerifierAgent().run(Draft("Use vpn.vectralogistics.example.", ["KB-007"], False), ZT_HITS, None).abstained
    assert not find_unsafe("Never disable antivirus or endpoint protection.")


def test_verifier_adds_p1_escalation():
    hits = [Hit("KB-005", "Printers", 0.6, "...", "")]
    v = VerifierAgent().run(Draft("Raise it as P1.", ["KB-005"], False), hits, "p1")
    assert "4357" in v.answer and v.citations == ["KB-005", "KB-003"]


def test_escalation_note_not_repeated_when_answer_has_the_number():
    hits = [Hit("KB-006", "Phishing", 0.6, "...", "")]
    v = VerifierAgent().run(Draft("Disconnect and call SecOps on ext. 7333.", ["KB-006"], False), hits, "security")
    assert v.answer.count("7333") == 1 and v.citations == ["KB-006"]
