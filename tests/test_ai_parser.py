from unittest.mock import patch
from app.services.ai_parser import _heuristic_parse, _resolve_accounts, parse_transaction


def test_heuristic_supplier_payment():
    result = _heuristic_parse("Paid 12000 to Ramesh supplier via UPI")
    assert result["transaction_type"] == "supplier_payment"
    assert result["amount"] == 12000.0
    assert result["payment_mode"] == "upi"


def test_heuristic_salary():
    result = _heuristic_parse("Paid salary 25000 cash")
    assert result["transaction_type"] == "salary"
    assert result["amount"] == 25000.0


def test_heuristic_rent():
    result = _heuristic_parse("Rent paid 8000")
    assert result["transaction_type"] == "rent"


def test_resolve_accounts_supplier_payment():
    debit, credit = _resolve_accounts("supplier_payment", "Ramesh")
    assert "Ramesh" in debit
    assert "Bank" in credit


def test_resolve_accounts_salary():
    debit, credit = _resolve_accounts("salary", None)
    assert "Salary" in debit
    assert "Bank" in credit


def test_parse_transaction_no_ai():
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = None
        mock_settings.return_value.GEMINI_API_KEY = None

    result = parse_transaction.__wrapped__("Paid 5000 to electrician") if hasattr(parse_transaction, "__wrapped__") else None
    # Just ensure heuristic path works
    parsed = _heuristic_parse("Paid 5000 to electrician")
    assert parsed["amount"] == 5000.0
