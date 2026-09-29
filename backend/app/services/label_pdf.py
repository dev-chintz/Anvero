"""Making Allegro's label PDF fill the label printer's 4 x 6 in paper.

Allegro's A6 label (a PDF made by OpenPDF) is one page of 297 x 420 pt with the
carrier's label placed on it as a form XObject, scaled to 95% and set 8 pt in
from the corner; the carrier's own drawing sits a few points further in. On
4 x 6 in paper, printed "fit to page width", the label came out at about 87% of
the paper's width. Cropping the page to the label was not enough: Chrome's
"fit to page" shrinks a page larger than the paper but never enlarges a smaller
one, so the cropped label printed at its own size in the paper's corner. So
each page is made exactly 4 x 6 in, and the label - what the page really draws
- is scaled up to fill it, centred.

The label's drawing is not rewritten: the page's content is wrapped between two
new content streams (a scale, and its undoing), added as an incremental update
to the file, so the barcode and the QR code are Allegro's own, only larger.
Anything this does not understand (a cross-reference stream, an encrypted file,
inline images) leaves the PDF as it came: a label printed smaller is better than
one printed wrong.
"""

import logging
import re
import zlib
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# left around the drawing, in points: the frame's lines have a width, and a
# label printer needs a hair of paper at the edge
MARGIN_PT = 1.5

# the label printer's paper, 4 x 6 in, in points
LABEL_PAGE_PT = (288, 432)

_WHITESPACE = b" \t\r\n\f\x00"
_DELIMITERS = b"()<>[]{}/%"

Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class _Unsupported(Exception):
    """Something in the PDF this module does not read; nothing is changed."""


@dataclass(frozen=True)
class _Ref:
    num: int
    gen: int


class _Name(str):
    pass


@dataclass
class _Op:
    name: str


class _Lexer:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def _skip(self) -> None:
        data, n = self.data, len(self.data)
        while self.pos < n:
            c = data[self.pos]
            if c in _WHITESPACE:
                self.pos += 1
            elif c == 0x25:  # % comment, to the end of the line
                while self.pos < n and data[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                return

    def token(self) -> Any:
        """The next token: a value, a structural marker ('<<', '[', ...) or an _Op."""
        self._skip()
        data = self.data
        if self.pos >= len(data):
            return None
        c = data[self.pos : self.pos + 1]
        two = data[self.pos : self.pos + 2]
        if two in (b"<<", b">>"):
            self.pos += 2
            return two.decode()
        if c in b"[]{}":
            self.pos += 1
            return c.decode()
        if c == b"(":
            return self._string()
        if c == b"<":
            end = data.index(b">", self.pos)
            self.pos = end + 1
            return b"<hex>"
        if c == b"/":
            start = self.pos = self.pos + 1
            while self.pos < len(data) and data[self.pos] not in _WHITESPACE + _DELIMITERS:
                self.pos += 1
            return _Name(data[start : self.pos].decode("latin-1"))
        start = self.pos
        while self.pos < len(data) and data[self.pos] not in _WHITESPACE + _DELIMITERS:
            self.pos += 1
        word = data[start : self.pos]
        if not word:
            raise _Unsupported(f"unexpected byte at {start}")
        try:
            return float(word) if b"." in word else int(word)
        except ValueError:
            return _Op(word.decode("latin-1"))

    def _string(self) -> bytes:
        data, depth = self.data, 0
        start = self.pos
        while self.pos < len(data):
            c = data[self.pos]
            if c == 0x5C:  # backslash: the next byte is escaped
                self.pos += 2
                continue
            if c == 0x28:
                depth += 1
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    self.pos += 1
                    return data[start : self.pos]
            self.pos += 1
        raise _Unsupported("unterminated string")

    def value(self, first: Any = None) -> Any:
        """One whole object: dictionaries and arrays read to their end, `n g R` a _Ref."""
        tok = self.token() if first is None else first
        if tok == "<<":
            result: dict[str, Any] = {}
            while (key := self.token()) != ">>":
                if not isinstance(key, _Name):
                    raise _Unsupported("dictionary key is not a name")
                result[key] = self.value()
            return result
        if tok == "[":
            items = []
            while (item := self.token()) != "]":
                items.append(self.value(item))
            return items
        if isinstance(tok, int):
            saved = self.pos
            gen, r = self.token(), self.token()
            if isinstance(gen, int) and isinstance(r, _Op) and r.name == "R":
                return _Ref(tok, gen)
            self.pos = saved
        return tok


class _Pdf:
    """Reading objects through a classic cross-reference table."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offsets: dict[int, tuple[int, int]] = {}
        match = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", data[-1024:])
        if not match:
            raise _Unsupported("no startxref")
        self.startxref = int(match.group(1))
        self.trailer_raw, self.trailer = self._read_xref(self.startxref)

    def _read_xref(self, offset: int) -> tuple[bytes, dict[str, Any]]:
        if self.data[offset : offset + 4] != b"xref":
            raise _Unsupported("cross-reference stream")
        lines = iter(self.data[offset + 4 :].splitlines())
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == b"trailer" or line.startswith(b"trailer"):
                break
            start, count = int(parts[0]), int(parts[1])
            for num in range(start, start + count):
                entry = next(lines).split()
                if entry[2] == b"n":
                    self.offsets.setdefault(num, (int(entry[0]), int(entry[1])))
        trailer_at = self.data.index(b"trailer", offset) + len(b"trailer")
        lexer = _Lexer(self.data, trailer_at)
        trailer = lexer.value()
        if not isinstance(trailer, dict):
            raise _Unsupported("trailer is not a dictionary")
        if "Encrypt" in trailer:
            raise _Unsupported("encrypted")
        if "XRefStm" in trailer:
            raise _Unsupported("hybrid cross-reference")
        raw = self.data[trailer_at : lexer.pos]
        if isinstance(trailer.get("Prev"), int):
            self._read_xref(trailer["Prev"])
        return raw, trailer

    def object(self, num: int) -> tuple[Any, int, int, int]:
        """The object's value, its generation, and where its value starts and ends."""
        offset, gen = self.offsets[num]
        lexer = _Lexer(self.data, offset)
        head = [lexer.token(), lexer.token(), lexer.token()]
        if head[0] != num or not (isinstance(head[2], _Op) and head[2].name == "obj"):
            raise _Unsupported(f"object {num} is not where the table says")
        start = lexer.pos
        value = lexer.value()
        return value, gen, start, lexer.pos

    def resolve(self, value: Any) -> Any:
        return self.object(value.num)[0] if isinstance(value, _Ref) else value

    def stream(self, num: int) -> tuple[dict[str, Any], bytes]:
        """A stream object's dictionary and decoded data."""
        head, _, _, end = self.object(num)
        match = re.compile(rb"\s*stream\r?\n").match(self.data, end)
        if not isinstance(head, dict) or not match:
            raise _Unsupported(f"object {num} is not a stream")
        length = self.resolve(head.get("Length"))
        if not isinstance(length, int):
            raise _Unsupported("stream without a length")
        raw = self.data[match.end() : match.end() + length]
        filters = head.get("Filter")
        filters = filters if isinstance(filters, list) else [filters] if filters else []
        if head.get("DecodeParms") or any(f != "FlateDecode" for f in filters):
            raise _Unsupported(f"stream {num} is encoded in a way not read here")
        return head, zlib.decompress(raw) if filters else raw


def _mul(a: Matrix, b: Matrix) -> Matrix:
    """a then b, as PDF composes matrices."""
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


class _Extents:
    """What a page draws: the points of its paths and images, and where its text starts."""

    def __init__(self, pdf: _Pdf) -> None:
        self.pdf = pdf
        self.shapes: list[tuple[float, float]] = []
        self.text: list[tuple[float, float]] = []
        # where the forms drawn directly by this content sit: nothing they
        # draw falls outside
        self.forms: list[tuple[float, float, float, float]] = []
        # whether this content shows text itself, rather than through a form
        self.own_text = False

    def run(self, content: bytes, resources: dict[str, Any], ctm: Matrix, depth: int = 0) -> None:
        if depth > 8:
            raise _Unsupported("forms nested too deep")
        xobjects = self.pdf.resolve(resources.get("XObject")) or {}
        lexer = _Lexer(content)
        operands: list[Any] = []
        stack: list[Matrix] = []
        tm = lm = _IDENTITY
        leading = 0.0
        while (tok := lexer.token()) is not None:
            if not isinstance(tok, _Op):
                operands.append(lexer.value(tok) if tok in ("[", "<<") else tok)
                continue
            op, args = tok.name, operands
            operands = []
            nums = [float(a) for a in args if isinstance(a, int | float)]
            if op == "q":
                stack.append(ctm)
            elif op == "Q":
                ctm = stack.pop() if stack else ctm
            elif op == "cm":
                ctm = _mul(tuple(nums[-6:]), ctm)  # type: ignore[arg-type]
            elif op in ("m", "l", "c", "v", "y"):
                self.shapes += [_apply(ctm, nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            elif op == "re":
                x, y, w, h = nums[-4:]
                self.shapes += [_apply(ctm, px, py) for px in (x, x + w) for py in (y, y + h)]
            elif op == "BT":
                tm = lm = _IDENTITY
            elif op == "Tm":
                tm = lm = tuple(nums[-6:])  # type: ignore[assignment]
            elif op in ("Td", "TD"):
                if op == "TD":
                    leading = -nums[-1]
                tm = lm = _mul((1, 0, 0, 1, nums[-2], nums[-1]), lm)
            elif op == "TL":
                leading = nums[-1]
            elif op in ("T*", "'", '"'):
                tm = lm = _mul((1, 0, 0, 1, 0, -leading), lm)
            if op in ("Tj", "TJ", "'", '"'):
                self.text.append(_apply(_mul(tm, ctm), 0, 0))
                self.own_text = True
            elif op == "Do":
                self._do(xobjects, args[-1], ctm, depth)
            elif op in ("BI", "sh", "d0", "d1"):
                raise _Unsupported(f"operator {op}")

    def _do(self, xobjects: dict[str, Any], name: Any, ctm: Matrix, depth: int) -> None:
        ref = xobjects.get(name)
        if not isinstance(ref, _Ref):
            raise _Unsupported(f"XObject {name} not found")
        head, _, _, _ = self.pdf.object(ref.num)
        if head.get("Subtype") == "Image":
            self.shapes += [_apply(ctm, x, y) for x in (0, 1) for y in (0, 1)]
            return
        if head.get("Subtype") != "Form":
            raise _Unsupported(f"XObject {name} is neither an image nor a form")
        _, content = self.pdf.stream(ref.num)
        matrix = tuple(float(v) for v in head.get("Matrix", _IDENTITY))
        form_ctm = _mul(matrix, ctm)  # type: ignore[arg-type]
        resources = self.pdf.resolve(head.get("Resources")) or {}
        inner = _Extents(self.pdf)
        inner.run(content, resources, form_ctm, depth + 1)
        # a form draws nothing outside its BBox
        bx0, by0, bx1, by1 = (float(v) for v in head["BBox"])
        corners = [_apply(form_ctm, x, y) for x in (bx0, bx1) for y in (by0, by1)]
        lo_x, hi_x = min(p[0] for p in corners), max(p[0] for p in corners)
        lo_y, hi_y = min(p[1] for p in corners), max(p[1] for p in corners)

        def clamp(p: tuple[float, float]) -> tuple[float, float]:
            return min(max(p[0], lo_x), hi_x), min(max(p[1], lo_y), hi_y)

        self.shapes += [clamp(p) for p in inner.shapes]
        self.text += [clamp(p) for p in inner.text]
        self.forms.append((lo_x, lo_y, hi_x, hi_y))


def _pages(pdf: _Pdf) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
    """Each page's object number, dictionary and (possibly inherited) resources."""
    root = pdf.resolve(pdf.trailer.get("Root"))
    found: list[tuple[int, dict[str, Any], dict[str, Any]]] = []

    def walk(ref: Any, resources: dict[str, Any], depth: int) -> None:
        if not isinstance(ref, _Ref) or depth > 16:
            raise _Unsupported("page tree")
        node = pdf.object(ref.num)[0]
        own = pdf.resolve(node.get("Resources"))
        resources = own if isinstance(own, dict) else resources
        if node.get("Type") == "Pages":
            for kid in pdf.resolve(node.get("Kids")) or []:
                walk(kid, resources, depth + 1)
        else:
            found.append((ref.num, node, resources))

    walk(root.get("Pages"), {}, 0)
    return found


def _label_box(pdf: _Pdf, page: dict[str, Any], resources: dict[str, Any]) -> list[float] | None:
    """Where on the page the label is, or None to leave the page as it is."""
    media = page.get("MediaBox")
    if not isinstance(media, list) or len(media) != 4:
        return None
    mx0, my0, mx1, my1 = (float(v) for v in media)
    contents = pdf.resolve(page.get("Contents"))
    refs = contents if isinstance(contents, list) else [page.get("Contents")]
    content = b"\n".join(pdf.stream(r.num)[1] for r in refs if isinstance(r, _Ref))
    extents = _Extents(pdf)
    extents.run(content, resources, _IDENTITY)
    if not extents.shapes:
        return None
    x0 = min(p[0] for p in extents.shapes) - MARGIN_PT
    y0 = min(p[1] for p in extents.shapes) - MARGIN_PT
    x1 = max(p[0] for p in extents.shapes) + MARGIN_PT
    y1 = max(p[1] for p in extents.shapes) + MARGIN_PT
    # text is known only by where it starts; any that starts outside the frame
    # the paths make, or too near its right or top edge to fit, could be cut.
    # Then the forms the page places are taken whole, as they clip what they
    # draw, or failing those the whole page
    if any(not (x0 <= x <= x1 - 4 and y0 <= y <= y1 - 4) for x, y in extents.text):
        if extents.forms and not extents.own_text:
            x0 = min(f[0] for f in extents.forms)
            y0 = min(f[1] for f in extents.forms)
            x1 = max(f[2] for f in extents.forms)
            y1 = max(f[3] for f in extents.forms)
        else:
            x0, y0, x1, y1 = mx0, my0, mx1, my1
    box = [max(x0, mx0), max(y0, my0), min(x1, mx1), min(y1, my1)]
    return box if box[2] - box[0] > 36 and box[3] - box[1] > 36 else None


def _num(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _fit(box: list[float]) -> bytes:
    """The content that scales `box` to fill the label page, centred and clipped to it."""
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    scale = min(LABEL_PAGE_PT[0] / width, LABEL_PAGE_PT[1] / height)
    tx = (LABEL_PAGE_PT[0] - width * scale) / 2 - x0 * scale
    ty = (LABEL_PAGE_PT[1] - height * scale) / 2 - y0 * scale
    matrix = " ".join(_num(v) for v in (scale, 0, 0, scale, tx, ty))
    clip = " ".join(_num(v) for v in (x0, y0, width, height))
    return f"q {matrix} cm {clip} re W n\n".encode()


def _stream_object(content: bytes) -> bytes:
    return b"<</Length %d>>stream\n" % len(content) + content + b"\nendstream"


def fit_label_pdf(data: bytes) -> bytes:
    """The label PDF with each page made 4 x 6 in and filled by the label; unchanged when unsure."""
    try:
        return _fit_pages(data)
    except Exception as exc:  # noqa: BLE001 - any doubt means the label as it came
        logger.info("Label PDF left as it came: %s", exc)
        return data


def _fit_pages(data: bytes) -> bytes:
    if not data.startswith(b"%PDF"):
        return data
    pdf = _Pdf(data)
    size = pdf.trailer.get("Size")
    if not isinstance(size, int):
        raise _Unsupported("trailer without a size")
    # one stream that undoes the scale, shared by every page, then one per page
    # that sets it
    closing = size
    size += 1
    new_objects: list[tuple[int, int, bytes]] = [(closing, 0, _stream_object(b"\nQ"))]
    for num, page, resources in _pages(pdf):
        box = _label_box(pdf, page, resources)
        if box is None:
            continue
        _, gen, start, end = pdf.object(num)
        body = data[start:end]
        contents = re.search(rb"/Contents\s*(\d+\s+\d+\s+R|\[[^\]]*\])", body)
        if not contents:
            continue
        opening = size
        size += 1
        new_objects.append((opening, 0, _stream_object(_fit(box))))
        inner = contents.group(1).strip(b"[]").strip()
        body = (
            body[: contents.start()]
            + b"/Contents[%d 0 R %s %d 0 R]" % (opening, inner, closing)
            + body[contents.end() :]
        )
        body = re.sub(rb"/(CropBox|TrimBox|BleedBox|ArtBox)\s*\[[^\]]*\]", b"", body)
        body = re.sub(rb"/MediaBox\s*\[[^\]]*\]", b"/MediaBox[0 0 %d %d]" % LABEL_PAGE_PT, body)
        new_objects.append((num, gen, body))
    if len(new_objects) == 1:
        return data

    out = bytearray(data if data.endswith(b"\n") else data + b"\n")
    entries = []
    for num, gen, body in new_objects:
        entries.append((num, gen, len(out)))
        out += b"%d %d obj\n" % (num, gen) + body.strip() + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n"
    for num, gen, offset in sorted(entries):
        out += b"%d 1\n%010d %05d n\r\n" % (num, offset, gen)
    trailer = re.sub(rb"/(Prev|Size)\s+\d+", b"", pdf.trailer_raw.strip())
    trailer = b"<</Size %d/Prev %d" % (size, pdf.startxref) + trailer[2:]
    out += b"trailer\n" + trailer + b"\nstartxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(out)
