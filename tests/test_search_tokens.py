"""Unit tests for search tsquery tokenization (no DB)."""
from mcp_server.tools import _fts_or_query


def test_strips_leading_apostrophe():
    assert _fts_or_query("'normal") == "normal"


def test_strips_trailing_apostrophe():
    assert _fts_or_query("normal'") == "normal"


def test_keeps_inner_apostrophes():
    assert _fts_or_query("don't") == "don't"
    assert _fts_or_query("ім'я") == "ім'я"


def test_mixed_tokens():
    assert _fts_or_query("'x | y") == "x | y"


def test_only_apostrophes_yields_none():
    assert _fts_or_query("'''") is None


def test_empty_query_yields_none():
    assert _fts_or_query("") is None


def test_uppercase_lowercased():
    assert _fts_or_query("'Blood Pressure") == "blood | pressure"
