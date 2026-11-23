"""A spender who has decided must be able to see how to pay, on /price/,
without a call. No account numbers or UPI IDs on the public page: those go
on the invoice."""
import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "price" / "index.html").read_text(encoding="utf-8")


def _section():
    m = re.search(r'<h2 id="pay">How to pay</h2>(.*?)(?=<h2|</section>)', PAGE, re.S)
    assert m, "no How to pay section"
    return m.group(1)


def test_how_to_pay_names_the_steps_and_the_methods():
    s = _section()
    for needed in ("GSTIN", "invoice", "UPI", "bank transfer", "48 hours", "fee back"):
        assert needed in s, needed


def test_how_to_pay_needs_no_call():
    assert "cal.com" not in _section()


def test_no_payment_identifiers_on_the_public_page():
    assert not re.search(r"\b[\w.\-]{2,}@(ok\w+|ybl|paytm|upi|ibl|axl)\b", PAGE)  # UPI ID
    assert not re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", PAGE)  # IFSC
    assert not re.search(r"\b\d{9,18}\b", PAGE)  # account number
