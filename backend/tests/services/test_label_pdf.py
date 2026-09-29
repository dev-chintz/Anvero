"""Cropping Allegro's label PDF to the label, on PDFs built like Allegro's."""

import zlib

from app.services.label_pdf import _pages, _Pdf, trim_label_pdf

# the carrier's label, drawn inside a form of 283.5 x 396.9 pt: a frame of
# lines from (6, 10) to (277, 391), a table cell, and text inside it
LABEL = b"""
q 6.45 358.65 82.7 32.1 re W* n
BT /F0 6 Tf 1 0 0 1 34.8 385 Tm (Oddz.)Tj ET Q
.5 w 6 10 m 6 391 l 277 391 l 277 10 l 6 10 l S
q 112.5 0 0 26.25 94.8 361.5 cm /Im0 Do Q
"""

# Allegro's page: the form scaled to 95% and set 8 pt in from the corner
PAGE = b"q\nBT\n36 384 Td\nET\nQ\nq 0.95 0 0 0.95 8 8 cm /Xf2 Do Q\n"


def _stream(head: bytes, data: bytes) -> bytes:
    packed = zlib.compress(data)
    return b"<<" + head + b"/Filter/FlateDecode/Length %d>>stream\n" % len(packed) + packed + b"\nendstream"


def _pdf(label: bytes = LABEL, pages: int = 1) -> bytes:
    """A PDF laid out as OpenPDF lays out Allegro's: one form per page."""
    objects: dict[int, bytes] = {
        1: b"<</Type/Catalog/Pages 2 0 R>>",
        3: _stream(
            b"/Type/XObject/Subtype/Form/Matrix[1 0 0 1 0 0]/BBox[0 0 283.5 396.9]"
            b"/Resources<</XObject<</Im0 4 0 R>>>>",
            label,
        ),
        4: b"<</Type/XObject/Subtype/Image/Width 1/Height 1/BitsPerComponent 8"
        b"/ColorSpace/DeviceGray/Length 1>>stream\n\x00\nendstream",
    }
    kids = []
    for i in range(pages):
        page, content = 10 + 2 * i, 11 + 2 * i
        objects[page] = (
            b"<</Contents %d 0 R/Type/Page/Resources<</XObject<</Xf2 3 0 R>>>>"
            b"/Parent 2 0 R/MediaBox[0 0 297 420]>>" % content
        )
        objects[content] = _stream(b"", PAGE)
        kids.append(b"%d 0 R" % page)
    objects[2] = b"<</Type/Pages/Kids[" + b" ".join(kids) + b"]/Count %d>>" % pages

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objects[num] + b"\nendobj\n"
    size = max(objects) + 1
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for num in range(1, size):
        out += b"%010d 00000 n \n" % offsets[num] if num in offsets else b"0000000000 65535 f \n"
    out += b"trailer\n<</ID [<ab><ab>]/Root 1 0 R/Size %d>>\nstartxref\n%d\n%%%%EOF\n" % (size, xref_at)
    return bytes(out)


def _boxes(data: bytes) -> list[list[float]]:
    pdf = _Pdf(data)
    return [[float(v) for v in page["MediaBox"]] for _, page, _ in _pages(pdf)]


def test_the_page_is_cropped_to_the_label_frame():
    original = _pdf()
    trimmed = trim_label_pdf(original)

    # the frame, 6..277 x 10..391 in the form, lands at 8 + 0.95 x on the page,
    # with 1.5 pt kept around it
    [box] = _boxes(trimmed)
    assert box == [12.2, 16, 272.65, 380.95]
    # the original is kept whole, the crop appended as an incremental update
    assert trimmed.startswith(original)
    assert b"/Prev " in trimmed[len(original) :]


def test_every_page_of_several_labels_is_cropped():
    assert _boxes(trim_label_pdf(_pdf(pages=3))) == [[12.2, 16, 272.65, 380.95]] * 3


def test_text_outside_the_frame_leaves_the_page_as_it_is():
    label = LABEL + b"BT /F0 6 Tf 1 0 0 1 20 3 Tm (Operator pocztowy)Tj ET\n"
    original = _pdf(label)
    assert trim_label_pdf(original) == original


def test_what_cannot_be_read_comes_back_unchanged():
    assert trim_label_pdf(b"%PDF-1.4 ship-1A6") == b"%PDF-1.4 ship-1A6"
    assert trim_label_pdf(b"not a pdf") == b"not a pdf"
    inline_image = _pdf(LABEL + b"BI /W 1 /H 1 ID \x00 EI\n")
    assert trim_label_pdf(inline_image) == inline_image
