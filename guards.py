"""Step 4/5 guardrails, shared by the MCP server, the agent callbacks and the Streamlit app.

Data tier   : is_sql_mutation (sqlparse syntax tree) + connect_ro (URI mode=ro, PRAGMA query_only,
              and a SQLite authorizer that only permits reads, so even a guard bypass cannot write).
Input tier  : mask_pii (Malaysian IC, phone, email, card with Luhn check, bank account) and
              detect_injection (prompt-injection phrases, normalised against simple obfuscation).
"""
import re
import sqlite3
import unicodedata
from pathlib import Path

import sqlparse
from sqlparse import tokens as T

# ---------------------------------------------------------------- data tier
WRITE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "ATTACH",
    "DETACH", "PRAGMA", "VACUUM", "REINDEX", "ANALYZE", "GRANT", "REVOKE", "UPSERT", "MERGE",
}


def is_sql_mutation(sql_query: str) -> bool:
    """True if the query is anything other than ONE plain SELECT (fail closed).

    Walks the sqlparse token tree instead of string matching, so keywords inside string
    literals ('delete me') are fine, but stacked statements (`SELECT 1; DROP ...`), CTE-wrapped
    writes (`WITH x AS (...) DELETE ...`) and SQLite admin verbs (ATTACH, PRAGMA, VACUUM INTO)
    are rejected. REPLACE is not in the keyword list on purpose: inside a single SELECT it can only
    be the string function replace(); `REPLACE INTO` is a non-SELECT statement and is refused above.
    """
    statements = [s for s in sqlparse.parse(sql_query or "") if s.token_first(skip_cm=True, skip_ws=True)]
    if len(statements) != 1:
        return True
    stmt = statements[0]
    if stmt.get_type() != "SELECT":
        return True
    for tok in stmt.flatten():
        if tok.ttype in T.Keyword or tok.ttype in T.Name.Builtin or tok.ttype in (T.DML, T.DDL):
            if tok.normalized.upper() in WRITE_KEYWORDS:
                return True
    return False


_READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _read_only_authorizer(action, arg1, arg2, db_name, trigger):
    # Third line of defence: the SQLite engine itself refuses anything that is not a read.
    return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY


def connect_ro(db_path) -> sqlite3.Connection:
    """Open the database physically read-only.

    Note `uri=True`: without it sqlite3 treats 'file:x.db?mode=ro' as a plain filename and
    silently CREATES a new, WRITABLE, empty database instead (tests/test_guards.py proves it).
    """
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")  # must run before the authorizer, which denies PRAGMA
    conn.set_authorizer(_read_only_authorizer)
    steps = [0]

    def _budget():  # abort runaway queries (accidental cartesian joins) after ~5M VM steps
        steps[0] += 1
        return 1 if steps[0] > 5000 else 0

    conn.set_progress_handler(_budget, 1000)
    return conn


# ---------------------------------------------------------------- input tier
def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MY_IC = re.compile(r"\b\d{6}-\d{2}-\d{4}\b|\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{6}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?60[- ]?|0)1\d[- ]?\d{3,4}[- ]?\d{4}(?!\d)|(?<!\d)\+?60[- ]?[3-9][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
_ACCOUNT = re.compile(r"(?<![\d.])\d{10,16}(?![\d.])")


def mask_pii(text: str) -> str:
    """Redact personal data before it reaches the model (and before tool output is shown)."""
    if not text:
        return text
    text = _EMAIL.sub("[EMAIL]", text)
    text = _MY_IC.sub("[MY_IC]", text)
    text = _CARD.sub(lambda m: "[CARD]" if _luhn_ok(re.sub(r"\D", "", m.group())) and 13 <= len(re.sub(r"\D", "", m.group())) <= 19 else m.group(), text)
    text = _PHONE.sub("[PHONE]", text)
    text = _ACCOUNT.sub("[BANK_ACCOUNT]", text)
    return text


def mask_pii_deep(value):
    """mask_pii applied to every string inside dicts/lists (tool responses)."""
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, dict):
        return {k: mask_pii_deep(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_pii_deep(v) for v in value]
    return value


_INJECTION = [
    (r"ignore (all |any |the )?(previous|prior|above|earlier|your) (instructions|rules|prompts?)", "override instructions"),
    (r"disregard (all |any |the |your )?(previous |prior )?(rules|instructions|guardrails|policies)", "override instructions"),
    (r"(reveal|show|print|repeat|leak) (me )?(your |the )?(system|hidden|developer) (prompt|instructions|message)", "prompt extraction"),
    (r"\byou are now\b|\bdeveloper mode\b|\bjailbreak\b|\bdo anything now\b|\bact as (an? )?(unrestricted|unfiltered)", "role hijack"),
    (r"(print|dump|list|export|show) (every|all|the full|full) .{0,40}(bank account|ic number|passwords?|card numbers?)", "bulk PII exfiltration"),
    (r"\b(drop|truncate|delete|alter)\s+(table|database|from)\b", "destructive SQL request"),
]
_INJECTION = [(re.compile(p, re.I), why) for p, why in _INJECTION]
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))


def detect_injection(text: str):
    """Return a reason string if the text looks like a prompt-injection / abuse attempt, else None.

    Normalises Unicode (NFKC), strips zero-width characters and collapses whitespace first.
    Limitation, stated honestly: a phrase list catches common attacks, not paraphrases; that is why
    the data tier must hold even when this tier is bypassed.
    """
    if not text:
        return None
    norm = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH))
    for rx, why in _INJECTION:
        if rx.search(norm):
            return why
    return None


def neutralise_embedded_instructions(text: str):
    """For tool output (documents, DB rows): cut out embedded instructions. Returns (text, found)."""
    found = False
    out = text
    for rx, _ in _INJECTION[:5]:
        if rx.search(out):
            found = True
            out = rx.sub("[REMOVED: embedded instruction]", out)
    # HTML comments are invisible to humans but visible to models: a classic hiding place.
    out, n = re.subn(r"<!--.*?-->", "[REMOVED: hidden comment]", out, flags=re.S)
    return out, found or n > 0
