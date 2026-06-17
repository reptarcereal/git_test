"""Tests for Spot.ai unit-number extraction (the nickname<->location matcher)."""
from app.spotai_client import extract_unit_numbers


def test_strips_prefix_and_leading_zeros():
    assert extract_unit_numbers("UNIT 002")[0] == "2"
    assert extract_unit_numbers("Unit 479")[0] == "479"


def test_matches_across_formats():
    # Starlink nickname and Spot.ai location reduce to the same unit number.
    assert extract_unit_numbers("Unit 118")[0] == extract_unit_numbers(
        "Site 118 - Phoenix"
    )[0]


def test_no_number_returns_empty():
    assert extract_unit_numbers("Starlink Mini Test") == []
    assert extract_unit_numbers(None) == []


def test_unit_number_found_alongside_other_numbers():
    # An address with a zip code still surfaces the unit number.
    assert "118" in extract_unit_numbers("118 Main St, Phoenix 85001")
