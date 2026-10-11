"""A tiny text-only PDF writer, so seeding needs no PDF library.

Produces one Letter page of Helvetica text that pypdf (and any viewer) can read back.
"""

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN = 54
LINE_HEIGHT = 15
MAX_LINES = (PAGE_HEIGHT - 2 * MARGIN) // LINE_HEIGHT


def _escape(text: str) -> str:
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(title: str, lines: list[str]) -> bytes:
    """Title in bold on the first line, then one PDF line per entry in `lines`."""
    content = [
        "BT",
        f"/F2 15 Tf {MARGIN} {PAGE_HEIGHT - MARGIN} Td ({_escape(title)}) Tj",
        f"/F1 10.5 Tf 0 -{LINE_HEIGHT * 2} Td",
    ]
    for line in lines[: MAX_LINES - 3]:
        content.append(f"({_escape(line)}) Tj 0 -{LINE_HEIGHT} Td")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            "/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>"
        ).encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(out)
