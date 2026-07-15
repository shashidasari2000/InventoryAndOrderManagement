"""
AI Parser Service - converts natural language to structured transaction data.
Uses OpenAI GPT as primary, Gemini as fallback.
"""
import json
import re
from typing import Optional
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

SYSTEM_PROMPT = """You are an Indian MSME accounting assistant. Parse the user's message and extract transaction details.

Return ONLY a valid JSON object with these fields:
{
  "transaction_type": one of ["supplier_payment", "customer_receipt", "salary", "rent", "electricity", "purchase", "sales", "other_expense", "other_income"],
  "party": "name of the person/entity involved (null if not mentioned)",
  "amount": numeric value only (no currency symbols),
  "payment_mode": one of ["cash", "upi", "bank_transfer", "cheque", "card", null],
  "narration": "brief description of the transaction in English",
  "confidence": number between 0 and 1
}

Rules:
- Amount must be a number (convert words like "twelve thousand" to 12000, "barah hazaar" to 12000)
- Detect language (English/Hindi/Telugu/Tamil/Kannada) and parse accordingly
- If amount cannot be determined, return null for amount
- Be conservative with confidence score
- Party extraction is CRITICAL: always extract the person/business name
  - "Paid X to Ramesh" → party: "Ramesh"
  - "Received X from Suresh" → party: "Suresh"
  - "Paid salary to Rajesh" → party: "Rajesh"
  - "Payment to ABC Traders" → party: "ABC Traders"
  - "Ramesh ko X diya" → party: "Ramesh"
  - "Suresh se X mila" → party: "Suresh"
- For payment_mode: "check"/"cheque" → "cheque", "neft"/"rtgs"/"imps" → "bank_transfer"
- transaction_type rules:
  - Paying a supplier/vendor/trader → "supplier_payment"
  - Receiving money from a customer → "customer_receipt"
  - Buying goods for resale → "purchase"
  - Selling goods → "sales"
"""

ACCOUNTING_RULES = {
    "supplier_payment": {
        "debit_account_template": "{party} A/c",
        "debit_account_fallback": "Sundry Creditors A/c",
        "credit_account": "Bank A/c",
        "voucher_type": "payment",
    },
    "customer_receipt": {
        "debit_account": "Bank A/c",
        "credit_account_template": "{party} A/c",
        "credit_account_fallback": "Sundry Debtors A/c",
        "voucher_type": "receipt",
    },
    "salary": {
        "debit_account": "Salary Expense A/c",
        "credit_account": "Bank A/c",
        "voucher_type": "payment",
    },
    "rent": {
        "debit_account": "Rent Expense A/c",
        "credit_account": "Bank A/c",
        "voucher_type": "payment",
    },
    "electricity": {
        "debit_account": "Electricity Expense A/c",
        "credit_account": "Bank A/c",
        "voucher_type": "payment",
    },
    "purchase": {
        "debit_account": "Purchase A/c",
        "credit_account_template": "{party} A/c",
        "credit_account_fallback": "Sundry Creditors A/c",
        "voucher_type": "purchase",
    },
    "sales": {
        "debit_account_template": "{party} A/c",
        "debit_account_fallback": "Sundry Debtors A/c",
        "credit_account": "Sales A/c",
        "voucher_type": "sales",
    },
    "other_expense": {
        "debit_account": "Miscellaneous Expense A/c",
        "credit_account": "Bank A/c",
        "voucher_type": "payment",
    },
    "other_income": {
        "debit_account": "Bank A/c",
        "credit_account": "Other Income A/c",
        "voucher_type": "receipt",
    },
}


def _resolve_accounts(transaction_type: str, party: Optional[str], payment_mode: Optional[str] = None) -> tuple[str, str]:
    rule = ACCOUNTING_RULES.get(transaction_type, ACCOUNTING_RULES["other_expense"])
    liquid_account = "Cash A/c" if payment_mode == "cash" else "Bank A/c"

    if party:
        debit_raw = rule.get("debit_account") or rule.get("debit_account_template", "").format(party=party)
        credit_raw = rule.get("credit_account") or rule.get("credit_account_template", "").format(party=party)
    else:
        debit_raw = rule.get("debit_account") or rule.get("debit_account_fallback", "Sundry Creditors A/c")
        credit_raw = rule.get("credit_account") or rule.get("credit_account_fallback", "Sundry Debtors A/c")

    debit = debit_raw.replace("Bank A/c", liquid_account)
    credit = credit_raw.replace("Bank A/c", liquid_account)
    return debit, credit


def _parse_with_openai(text: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _parse_with_groq(text: str) -> dict:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _parse_with_gemini(text: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    prompt = f"{SYSTEM_PROMPT}\n\nUser message: {text}\n\nReturn only JSON."
    response = model.generate_content(prompt)
    raw = response.text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("No JSON found in Gemini response")


def parse_transaction(text: str) -> dict:
    """
    Parse natural language into structured transaction + accounting entry.
    Returns dict with keys: transaction_type, party, amount, payment_mode,
    narration, debit_account, credit_account, voucher_type, confidence, raw_text
    """
    parsed = None
    error = None

    # Try OpenAI first
    if settings.OPENAI_API_KEY:
        try:
            parsed = _parse_with_openai(text)
            logger.info("ai_parse_success", provider="openai", text=text[:50])
        except Exception as e:
            error = str(e)
            logger.warning("openai_parse_failed", error=error)

    # Fallback to Groq (free, no quota issues)
    if parsed is None and settings.GROQ_API_KEY:
        try:
            parsed = _parse_with_groq(text)
            logger.info("ai_parse_success", provider="groq", text=text[:50])
        except Exception as e:
            error = str(e)
            logger.warning("groq_parse_failed", error=error)

    # Fallback to Gemini
    if parsed is None and settings.GEMINI_API_KEY:
        try:
            parsed = _parse_with_gemini(text)
            logger.info("ai_parse_success", provider="gemini", text=text[:50])
        except Exception as e:
            error = str(e)
            logger.warning("gemini_parse_failed", error=error)

    # Final fallback: basic rule-based heuristic
    if parsed is None:
        logger.warning("ai_parse_fallback_heuristic", error=error)
        parsed = _heuristic_parse(text)

    transaction_type = parsed.get("transaction_type", "other_expense")
    party = parsed.get("party")
    payment_mode = parsed.get("payment_mode")
    debit_account, credit_account = _resolve_accounts(transaction_type, party, payment_mode)

    rule = ACCOUNTING_RULES.get(transaction_type, ACCOUNTING_RULES["other_expense"])
    return {
        "transaction_type": transaction_type,
        "party": party,
        "amount": parsed.get("amount"),
        "payment_mode": parsed.get("payment_mode"),
        "narration": parsed.get("narration", text[:200]),
        "debit_account": debit_account,
        "credit_account": credit_account,
        "voucher_type": rule["voucher_type"],
        "confidence": parsed.get("confidence", 0.5),
        "raw_text": text,
    }


def _heuristic_parse(text: str) -> dict:
    """Simple keyword-based fallback when AI is unavailable."""
    text_lower = text.lower()
    amount = None
    amount_match = re.search(r"[\u20b9rs\.]*\s*(\d[\d,]*\.?\d*)", text_lower)
    if amount_match:
        amount = float(amount_match.group(1).replace(",", ""))

    if any(w in text_lower for w in ["salary", "wages", "staff"]):
        txn_type = "salary"
    elif any(w in text_lower for w in ["rent"]):
        txn_type = "rent"
    elif any(w in text_lower for w in ["electricity", "electric", "bijli"]):
        txn_type = "electricity"
    elif any(w in text_lower for w in ["purchase", "bought", "kharida"]):
        txn_type = "purchase"
    elif any(w in text_lower for w in ["sale", "sold", "becha"]):
        txn_type = "sales"
    elif any(w in text_lower for w in ["received", "mila", "paisa aaya"]):
        txn_type = "customer_receipt"
    elif any(w in text_lower for w in ["paid", "payment", "diya"]):
        txn_type = "supplier_payment"
    else:
        txn_type = "other_expense"

    payment_mode = None
    if "upi" in text_lower:
        payment_mode = "upi"
    elif "cash" in text_lower:
        payment_mode = "cash"
    elif "cheque" in text_lower or "check" in text_lower:
        payment_mode = "cheque"

    return {
        "transaction_type": txn_type,
        "party": None,
        "amount": amount,
        "payment_mode": payment_mode,
        "narration": text[:200],
        "confidence": 0.3,
    }
