"""Tests for Spot.ai unit-token extraction (the nickname<->location matcher)."""
from app.spotai_client import extract_unit_tokens


def test_spaced_label_is_ignored_only_number_matters():
    # "Unit"/"Site" are descriptive labels; only the number identifies the unit.
    assert extract_unit_tokens("UNIT 002") == ["2"]
    assert extract_unit_tokens("Unit 479") == ["479"]
    assert extract_unit_tokens("Site 118 - Phoenix") == ["118"]


def test_glued_prefix_is_significant():
    # A glued series code like VX is part of the identity.
    assert extract_unit_tokens("VX002") == ["VX2"]
    assert extract_unit_tokens("VX-002") == ["VX2"]


def test_vx_and_unit_are_different_units():
    # The key bug: "Unit 002" must NOT match "VX002".
    assert extract_unit_tokens("Unit 002") != extract_unit_tokens("VX002")
    assert extract_unit_tokens("Unit 002") == ["2"]
    assert extract_unit_tokens("VX002") == ["VX2"]


def test_format_differences_still_match():
    # Same unit, different formatting on each system -> same token.
    assert extract_unit_tokens("Unit 118")[0] == extract_unit_tokens("118")[0]


def test_no_number_returns_empty():
    assert extract_unit_tokens("Starlink Mini Test") == []
    assert extract_unit_tokens(None) == []
