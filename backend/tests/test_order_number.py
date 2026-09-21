import pytest

from app.core.order_number import format_order_number, parse_order_number


def test_formats_with_the_prefix_and_zero_padding():
    assert format_order_number(1) == "AN-000001"
    assert format_order_number(123) == "AN-000123"


def test_a_number_wider_than_the_padding_is_not_cut():
    assert format_order_number(1234567) == "AN-1234567"


@pytest.mark.parametrize(
    "text", ["AN-000123", "an-000123", " AN-123 ", "000123", "123"]
)
def test_understands_what_a_person_would_type(text):
    assert parse_order_number(text) == 123


@pytest.mark.parametrize(
    "text", ["", "AN-", "ALG-1234", "buyer@example.com", "12a", "0", "-5", "١٢٣", "99999999999"]
)
def test_leaves_everything_else_to_the_other_search_fields(text):
    assert parse_order_number(text) is None
