from vectra.evaluation.cases import ANAND
from vectra.privacy import mask, scrub


def test_anand_is_masked():
    m = mask(ANAND)
    for secret in ("Anand", "Sharma", "anand.sharma@", "9876543210"):
        assert secret not in m.text
    assert m.found == {"NAME": 1, "EMAIL": 1, "PHONE": 1}
    assert "iPhone" in m.text


def test_cut_off_email_is_masked():
    m = mask("Hi, I'm Anand Sharma (anand.sharma@…, +91 9876543210)")
    assert "anand" not in m.text.lower() and m.found == {"NAME": 1, "EMAIL": 1, "PHONE": 1}


def test_masking_leaves_kb_terms_alone():
    for text in ("ZenTunnel shows ZT-401", "error 0x80070005", "phone ext. 4357",
                 "What is the P2 target?", "port 10443", "UDP 51820"):
        assert mask(text).text == text


def test_scrub_removes_echoed_pii():
    cleaned, changed = scrub("Hi Anand, write to anand.sharma@vectralogistics.example or call 9876543210.")
    assert changed and "@" not in cleaned and "9876543210" not in cleaned
