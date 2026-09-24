import re
from datetime import UTC, datetime
from decimal import Decimal

from app.schemas.shipping import PackageSize, ShippingSender, ShippingSettings
from app.services.sample_label import build_sample_label

NOW = datetime(2026, 9, 24, 20, 12, tzinfo=UTC)


def _settings(**sender_overrides) -> ShippingSettings:
    sender = {
        "name": "Jan Kowalski",
        "company": None,
        "street": "Długa 1",
        "postal_code": "00-001",
        "city": "Łódź",
        "country_code": "PL",
        "email": "sklep@example.com",
        "phone": "500600700",
    }
    return ShippingSettings(
        sender=ShippingSender(**{**sender, **sender_overrides}),
        default_package=PackageSize(
            length_cm=Decimal(30),
            width_cm=Decimal("20.5"),
            height_cm=Decimal(10),
            weight_kg=Decimal("1.500"),
        ),
    )


def _text_of(pdf: bytes) -> str:
    """What the page prints, from its `(text) Tj` operators."""
    return "\n".join(m.decode("latin-1") for m in re.findall(rb"\((.*?)\) Tj", pdf, flags=re.DOTALL))


def test_it_is_a_one_page_a6_pdf():
    pdf = build_sample_label(_settings(), NOW)

    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page ") == 1
    # 105 x 148 mm in points
    assert b"/MediaBox [0 0 297.64 419.53]" in pdf


def test_its_cross_reference_table_points_at_the_objects():
    """A viewer that finds the table wrong has to repair the file, and a
    printer driver may not."""
    pdf = build_sample_label(_settings(), NOW)

    start = int(re.search(rb"startxref\n(\d+)\n%%EOF", pdf).group(1))
    assert pdf[start : start + 4] == b"xref"
    entries = re.findall(rb"(\d{10}) 00000 n ", pdf[start:])
    assert len(entries) == 6
    for number, offset in enumerate(entries, start=1):
        assert pdf[int(offset) :].startswith(f"{number} 0 obj".encode("ascii"))


def test_its_stream_length_is_the_length_of_its_content():
    pdf = build_sample_label(_settings(), NOW)

    declared = int(re.search(rb"/Length (\d+) >>\nstream\n", pdf).group(1))
    stream = re.search(rb"stream\n(.*)\nendstream", pdf, flags=re.DOTALL).group(1)
    assert declared == len(stream)


def test_it_prints_the_sender_and_the_default_parcel_from_settings():
    text = _text_of(build_sample_label(_settings(), NOW))

    assert "Jan Kowalski" in text
    assert "00-001 Lodz PL" in text
    assert "sklep@example.com  500600700" in text
    assert "Default parcel: 30 x 20.5 x 10 cm, 1.5 kg" in text
    assert "Made: 2026-09-24 20:12 UTC" in text


def test_polish_letters_are_printed_without_their_marks():
    """The standard fonts have none, and a missing glyph would print as a gap."""
    text = _text_of(build_sample_label(_settings(street="Żółć Gęślą 5", name="Łukasz Ćwik"), NOW))

    assert "Zolc Gesla 5" in text
    assert "Lukasz Cwik" in text
    assert not any(ord(character) > 127 for character in text)


def test_text_cannot_break_out_of_its_string():
    pdf = build_sample_label(_settings(company=r"Acme (Test) \ Co"), NOW)

    # a parenthesis or a backslash in the text is escaped, so it cannot end the string early
    assert rb"(Acme \(Test\) \\ Co) Tj" in pdf


def test_it_still_works_before_anything_is_set_up():
    text = _text_of(build_sample_label(ShippingSettings(), NOW))

    assert "Sender: not set yet" in text
    assert "Default parcel: not set yet" in text
