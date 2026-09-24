"""A sample A6 label, drawn here, for checking that labels can be shown and printed.

Real labels are PDFs Allegro makes when a shipment is bought, which costs
money and only works with an Allegro account (`shipping_labels.py`). This one
is made by Anvero alone: nothing is bought, nothing is sent, safe mode does
not matter. It answers the questions that come before any parcel: does the PDF
open, does the printer take A6 at its true size, are the margins kept, and is
fine print, the kind a barcode is made of, printed sharp.

The page is written by hand as a one-page PDF with the standard Helvetica
fonts, so no PDF library is needed for it. Those fonts have no Polish letters,
so the sender's text is printed without diacritics.
"""

import unicodedata
from datetime import UTC, datetime

from app.schemas.shipping import ShippingSettings

# A6, in millimetres, and PDF points (1/72 inch)
PAGE_WIDTH_MM = 105.0
PAGE_HEIGHT_MM = 148.0
_PT_PER_MM = 72.0 / 25.4

# a thermal label printer's dot at 203 dpi, the common resolution
DOT_MM = 25.4 / 203


def _pt(mm: float) -> float:
    return mm * _PT_PER_MM


def _num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _plain(text: str) -> str:
    """The text as the standard fonts can print it: no diacritics, no surprises."""
    stripped = text.replace("ł", "l").replace("Ł", "L")
    decomposed = unicodedata.normalize("NFKD", stripped)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Page:
    """Drawing on the page in millimetres from its top-left corner, as a
    label is read."""

    def __init__(self) -> None:
        self._ops: list[str] = []

    def _y(self, top_mm: float) -> float:
        return _pt(PAGE_HEIGHT_MM - top_mm)

    def line_width(self, mm: float) -> None:
        self._ops.append(f"{_num(_pt(mm))} w")

    def rect(self, x: float, top: float, width: float, height: float, fill: bool = False) -> None:
        # a rectangle is given by its lower-left corner
        self._ops.append(
            f"{_num(_pt(x))} {_num(self._y(top + height))} {_num(_pt(width))} {_num(_pt(height))} re "
            + ("f" if fill else "S")
        )

    def line(self, x1: float, top1: float, x2: float, top2: float) -> None:
        self._ops.append(
            f"{_num(_pt(x1))} {_num(self._y(top1))} m {_num(_pt(x2))} {_num(self._y(top2))} l S"
        )

    def text(self, x: float, baseline: float, size: float, text: str, bold: bool = False) -> None:
        font = "F2" if bold else "F1"
        self._ops.append(
            f"BT /{font} {_num(size)} Tf {_num(_pt(x))} {_num(self._y(baseline))} Td "
            f"({_escape(_plain(text))}) Tj ET"
        )

    def content(self) -> bytes:
        return "\n".join(self._ops).encode("ascii")


def _sender_lines(settings: ShippingSettings) -> list[str]:
    sender = settings.sender
    if sender is None:
        return ["Sender: not set yet (Settings > Shipping)"]
    lines = ["Sender (as printed on real labels)"]
    lines.append(sender.name)
    if sender.company:
        lines.append(sender.company)
    lines.append(sender.street)
    lines.append(f"{sender.postal_code} {sender.city} {sender.country_code}")
    lines.append(f"{sender.email}  {sender.phone}")
    return lines


def _parcel_line(settings: ShippingSettings) -> str:
    package = settings.default_package
    if package is None:
        return "Default parcel: not set yet (Settings > Shipping)"
    return (
        f"Default parcel: {package.length_cm.normalize():f} x {package.width_cm.normalize():f} x "
        f"{package.height_cm.normalize():f} cm, {package.weight_kg.normalize():f} kg"
    )


def _draw(settings: ShippingSettings, now: datetime) -> bytes:
    page = _Page()

    # the frame 2 mm from the edge and a square in each corner inside it: a
    # printer or a print dialog that clips or shifts the page cuts these off
    page.line_width(0.4)
    page.rect(2, 2, PAGE_WIDTH_MM - 4, PAGE_HEIGHT_MM - 4)
    for x in (4, PAGE_WIDTH_MM - 7):
        for top in (4, PAGE_HEIGHT_MM - 7):
            page.rect(x, top, 3, 3, fill=True)

    page.text(11, 15, 24, "TEST LABEL", bold=True)
    page.text(11, 20, 7, "Made by Anvero. Nothing was bought and nothing was sent.")

    top = 27
    page.text(11, top, 8, "Page: A6, 105 x 148 mm", bold=True)
    top += 3.8
    page.text(11, top, 8, f"Made: {now.astimezone(UTC):%Y-%m-%d %H:%M} UTC")
    top += 5
    for line in _sender_lines(settings):
        page.text(11, top, 8, line)
        top += 3.6
    top += 1.4
    page.text(11, top, 8, _parcel_line(settings))

    # a ruler exactly 100 mm long: if a print measures otherwise, it was scaled
    ruler_top = 76
    left = 2.5
    page.line_width(0.25)
    page.line(left, ruler_top, left + 100, ruler_top)
    for mm in range(101):
        height = 4.5 if mm % 10 == 0 else 3 if mm % 5 == 0 else 1.5
        page.line(left + mm, ruler_top, left + mm, ruler_top + height)
    for cm in range(11):
        label_x = left + cm * 10 - (0.8 if cm < 10 else 1.6)
        page.text(label_x, ruler_top + 8.5, 6, str(cm))
    page.text(11, ruler_top + 13, 6, "Ruler: 10 cm. Any other length means the print was scaled.")
    page.text(11, ruler_top + 16.5, 6, "Print at 100% / actual size, not 'fit to page'.")

    # lines of 1 to 4 printer dots: the finest one is what a barcode is made of
    chart_top = 100
    page.text(11, chart_top - 1.5, 6, "Fine lines, 1 to 4 dots wide (203 dpi)")
    x = 11.0
    for dots in (1, 2, 3, 4):
        width = dots * DOT_MM
        group_start = x
        page.line_width(width)
        for _ in range(10):
            page.line(x + width / 2, chart_top, x + width / 2, chart_top + 8)
            x += 2 * width
        page.text(group_start, chart_top + 11, 6, f"{dots}")
        x += 3
    page.rect(64, chart_top, 30, 8, fill=True)
    page.text(64, chart_top + 11, 6, "Solid black")

    # text as small as a label carries it
    sample = "Aa Bb Cc 0123456789"
    for baseline, size in ((121, 6), (125.5, 8), (130.5, 10), (136, 12)):
        page.text(11, baseline, size, f"{sample}  {size} pt")

    page.text(11, 143, 6, "Real labels come from Allegro (Wysylam z Allegro) as A6 PDFs.")
    return page.content()


def build_sample_label(settings: ShippingSettings, now: datetime | None = None) -> bytes:
    """The sample label as a PDF: one A6 page."""
    content = _draw(settings, now or datetime.now(UTC))
    width, height = _num(_pt(PAGE_WIDTH_MM)), _num(_pt(PAGE_HEIGHT_MM))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>"
        ).encode("ascii"),
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    # the second line of bytes above 127 tells tools the file is binary
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)
