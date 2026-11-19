"""Dependency-free synthetic PDF inputs owned by this project."""


def _literal(text: str) -> str:
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _text(x: int, y: int, text: str) -> bytes:
    return f"BT /F1 12 Tf 1 0 0 1 {x} {y} Tm {_literal(text)} Tj ET\n".encode("ascii")


def _line(y: int, *columns: tuple[int, str]) -> bytes:
    return b"".join(_text(x, y, value) for x, value in columns)


def _table_line(y: int, metric: str, current: str, previous: str) -> bytes:
    return _line(y, (36, metric), (315, current), (420, previous))


def _stream(commands: bytes) -> bytes:
    return f"<< /Length {len(commands)} >>\nstream\n".encode("ascii") + commands + b"endstream"


def _document(*pages: tuple[str, bytes]) -> bytes:
    labels = " ".join(f"{index} << /P {_literal(label)} >>" for index, (label, _) in enumerate(pages))
    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(len(pages)))
    objects = [
        f"<< /Type /Catalog /Pages 2 0 R /PageLabels << /Nums [{labels}] >> >>".encode("ascii"),
        f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for _, commands in pages:
        stream_number = len(objects) + 2
        objects.extend((
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 520 420] /Contents {stream_number} 0 R "
             "/Resources << /Font << /F1 3 0 R >> >> >>").encode("ascii"),
            _stream(commands),
        ))

    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref = len(data)
    size = len(objects) + 1
    data.extend(f"xref\n0 {size}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(data)


def own_paginated_pdf() -> bytes:
    """Two labeled pages with native text, repeated columns and a continuation."""
    units = _text(36, 362, "Currency and scale: RUB million")
    header = _table_line(320, "Metric", "2025", "2024")
    first = (
        _text(36, 390, "Synthetic financial statement") + units + header
        + _table_line(294, "Operating revenue", "120", "100")
        + _table_line(268, "Operating profit", "18", "-4")
        + _text(36, 24, "Page 7")
    )
    second = (
        _text(36, 390, "Continuation of the financial table") + units + header
        + _table_line(294, "Total assets", "300", "280")
        + _table_line(268, "Net cash flow", "-5", "12")
        + _text(36, 24, "Page 8")
    )
    return _document(("Statement-A", first), ("Statement-B", second))


def own_scan_pdf() -> bytes:
    """One page with an embedded bitmap and no text operators."""
    commands = b"q\n200 0 0 200 36 100 cm\nBI\n/W 8 /H 8 /CS /G /BPC 1 /F /AHx\nID\nFFC3BDADB5BDC3FF>\nEI\nQ\n"
    return _document(("Scan-A", commands))


def own_unlabeled_pdf() -> bytes:
    """Four aligned numbers with no headers, labels, currency or scale."""
    commands = _line(320, (315, "120"), (420, "100")) + _line(294, (315, "-5"), (420, "12"))
    return _document(("Unlabeled-A", commands))
