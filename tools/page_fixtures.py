"""Reproducible PDF declarations for the page-tree reader's fixture contracts.

ISO 32000-1 §§7.5.4, 7.5.7, 7.5.8, 7.7.3.2 and Annex F. No PDF library,
external executable, or hand-maintained binary is needed to rebuild these.
"""
import re
import zlib

XMP = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
       b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" '
       b'pdfaid:part="2" pdfaid:conformance="b"/></rdf:RDF></x:xmpmeta>')


def stream(body, extra=b""):
    return b"<< /Length " + str(len(body)).encode("ascii") + extra + b" >>\nstream\n" + body + b"\nendstream"


def objects(count, leaves=None, portfolio=False):
    leaves = count if leaves is None else leaves
    kids = b" ".join(f"{n} 0 R".encode("ascii") for n in range(3, 3 + leaves))
    result = {
        1: b"<< /Type /Catalog /Pages 2 0 R /Metadata 100 0 R"
           + (b" /Collection << >>" if portfolio else b"") + b" >>",
        2: b"<< /Type /Pages /Count " + str(count).encode("ascii") + b" /Kids [" + kids + b"] >>",
        100: stream(XMP, b" /Type /Metadata /Subtype /XML"),
    }
    for n in range(3, 3 + leaves):
        result[n] = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>"
    return result


def append_revision(base, values, root=1, prev=None, extra=b""):
    data = bytearray(base)
    positions = {}
    for number, body in sorted(values.items()):
        positions[number] = len(data)
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    at = len(data)
    data.extend(b"xref\n")
    if not base.endswith(b"\n") or b"startxref" not in base:
        size = max(values) + 1
        data.extend(f"0 {size}\n".encode("ascii"))
        for number in range(size):
            data.extend((f"{positions[number]:010d} 00000 n \n" if number in positions
                         else "0000000000 65535 f \n").encode("ascii"))
    else:
        size = max(max(values), 100) + 1
        for number in sorted(values):
            data.extend(f"{number} 1\n{positions[number]:010d} 00000 n \n".encode("ascii"))
    trailer = f"<< /Size {size}".encode("ascii")
    if root is not None:
        trailer += f" /Root {root} 0 R".encode("ascii")
    if prev is not None:
        trailer += f" /Prev {prev}".encode("ascii")
    data.extend(b"trailer\n" + trailer + extra + b" >>\nstartxref\n" + str(at).encode("ascii") + b"\n%%EOF\n")
    return bytes(data)


def classic(count=7, leaves=None, encrypted=False, portfolio=False, cycle=False, padding=0, unconfirmed=False):
    values = objects(count, leaves, portfolio)
    if cycle:
        values[1] = b"<< /Type /Catalog /Pages 1 0 R /Metadata 100 0 R >>"
    if padding:
        values[2] = b"<< /Padding (" + b"x" * padding + b") /Count " + str(count).encode("ascii") + b" >>"
    prefix = b"%PDF-1.7\n" + (b"% " + b"obj " * 100_000 + b"\n" if unconfirmed else b"")
    return append_revision(prefix, values, extra=b" /Encrypt 99 0 R" if encrypted else b"")


def incremental():
    initial = classic(2)
    previous = int(re.findall(rb"startxref\n([0-9]+)", initial)[-1])
    return append_revision(initial, {
        2: b"<< /Type /Pages /Count 3 /Kids [3 0 R 4 0 R 5 0 R] >>",
        5: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",
    }, root=None, prev=previous)


def prev_cycle():
    base = classic()
    at = base.index(b"xref\n")
    return base.replace(b" /Root 1 0 R", f" /Root 1 0 R /Prev {at}".encode("ascii"), 1)


def _write_objects(data, values, headers=None):
    positions = {}
    for number, body in sorted(values.items()):
        positions[number] = len(data)
        identity, generation = (headers or {}).get(number, (number, 0))
        data.extend(f"{identity} {generation} obj\n".encode("ascii") + body + b"\nendobj\n")
    return positions


def _write_table(data, positions, ranges=None, size=None, extra=b"", rows=None, row_width=20):
    actual_size = max(positions) + 1
    at = len(data)
    data.extend(b"xref\n")
    for first, count in ranges or [(0, actual_size)]:
        data.extend(f"{first} {count}\n".encode("ascii"))
        for number in range(first, first + count):
            offset = positions.get(number, 0)
            generation, kind = (rows or {}).get(number, (0, "n") if offset else (65535, "f"))
            row = f"{offset:010d} {generation:05d} {kind} \n".encode("ascii")
            if row_width == 19:
                row = row[:-2] + b"\n"
            elif row_width == 21:
                row = row[:-1] + b" \n"
            data.extend(row)
    data.extend(f"trailer\n<< /Size {actual_size if size is None else size} /Root 1 0 R".encode("ascii")
                + extra + b" >>\nstartxref\n" + str(at).encode("ascii") + b"\n%%EOF\n")
    return bytes(data)


def table_pdf(total=101, ranges=None, size=None, rows=None, headers=None, row_width=20):
    """ISO 32000-1 §7.5.4: fixed-width rows, including sparse subsections."""
    values = objects(7)
    values.update({number: b"0" for number in range(10, total) if number != 100})
    data = bytearray(b"%PDF-1.7\n")
    positions = _write_objects(data, values, headers)
    return _write_table(data, positions, ranges, size, rows=rows, row_width=row_width)


def hybrid(conflict=False, pages_in_stream=False, previous=False):
    """§7.5.8.4: table, its supplementary stream, then the previous section."""
    data = bytearray(b"%PDF-1.7\n")
    values = objects(7)
    values[200] = b"<< /Marker /Hidden >>"
    positions = _write_objects(data, values)
    stream_positions = {200: positions[200]}
    if conflict:
        stream_positions[2] = len(data)
        data.extend(b"2 0 obj\n<< /Type /Pages /Count 99 >>\nendobj\n")
    elif pages_in_stream:
        stream_positions[2] = positions[2]
    index = b" ".join(f"{number} 1".encode("ascii") for number in sorted(stream_positions))
    payload = b"".join(b"\x01" + stream_positions[number].to_bytes(4, "big") + b"\x00\x00"
                       for number in sorted(stream_positions))
    xref = len(data)
    data.extend(b"103 0 obj\n" + stream(zlib.compress(payload),
                b" /Type /XRef /Size 201 /W [1 4 2] /Index [" + index + b"] /Filter /FlateDecode")
                + b"\nendobj\n")
    table = {number: at for number, at in positions.items() if number != 200
             and not (pages_in_stream and number == 2)}
    table[103] = xref
    result = _write_table(data, table, [(number, 1) for number in sorted(table)],
                          size=201, extra=f" /XRefStm {xref}".encode("ascii"))
    if previous:
        at = int(re.findall(rb"startxref\n([0-9]+)", result)[-1])
        result = append_revision(result, {201: b"0"}, root=None, prev=at)
    return result


def compressed(count=7, predictor=False, object_cycle=False, compressed_claim=False, overlap=False):
    values = objects(count)
    if compressed_claim:
        values[100] = stream(zlib.compress(XMP), b" /Type /Metadata /Subtype /XML /Filter /FlateDecode")
    catalog, pages = values.pop(1), values.pop(2)
    first_body = catalog + b"\n"
    header = f"1 0 2 {len(first_body)} ".encode("ascii")
    payload = header + first_body + pages
    values[102] = stream(zlib.compress(payload),
                         f" /Type /ObjStm /N 2 /First {len(header)} /Filter /FlateDecode".encode("ascii"))
    data = bytearray(b"%PDF-1.7\n")
    positions = {}
    for number, body in sorted(values.items()):
        positions[number] = len(data)
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    at = positions[103] = len(data)
    rows = []
    for number in range(104):
        if object_cycle and number == 102:
            row = b"\x02" + (102).to_bytes(4, "big") + b"\x00\x00"
        elif number in (1, 2):
            row = b"\x02" + (102).to_bytes(4, "big") + (number - 1).to_bytes(2, "big")
        elif number in positions:
            row = b"\x01" + positions[number].to_bytes(4, "big") + b"\x00\x00"
        else:
            row = b"\x00" * 5 + b"\xff\xff"
        rows.append(row)
    payload = b"".join(rows)
    extra = b" /Type /XRef /Size 104 /Root 1 0 R /W [1 4 2] /Index [0 104] /Filter /FlateDecode"
    if overlap:
        extra = extra.replace(b"/Index [0 104]", b"/Index [0 60 50 44]")
    if predictor:
        previous = bytes(7)
        encoded = []
        for row in rows:
            encoded.append(b"\x02" + bytes((x - y) % 256 for x, y in zip(row, previous)))
            previous = row
        payload = b"".join(encoded)
        extra += b" /DecodeParms << /Predictor 12 /Columns 7 >>"
    data.extend(b"103 0 obj\n" + stream(zlib.compress(payload), extra) + b"\nendobj\n"
                + b"startxref\n" + str(at).encode("ascii") + b"\n%%EOF\n")
    return bytes(data)


def linearized():
    """Annex F's first-page xref -> forward Prev -> main xref layout."""
    values = objects(7)
    prefix = (b"%PDF-1.7\n150 0 obj\n<< /Linearized 1 /L 0000000000 /H [0 0] "
              b"/O 3 /E 0000000000 /N 7 /T 0000000000 >>\nendobj\n")
    first = len(prefix)
    front = (b"xref\n1 2\n0000000000 00000 n \n0000000000 00000 n \n"
             b"trailer\n<< /Size 151 /Root 1 0 R /Prev 0000000000 >>\n")
    data = bytearray(prefix + front)
    positions = {150: 9}
    for number, body in sorted(values.items()):
        positions[number] = len(data)
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    main = len(data)
    data.extend(b"xref\n0 151\n")
    for number in range(151):
        data.extend((f"{positions[number]:010d} 00000 n \n" if number in positions
                     else "0000000000 65535 f \n").encode("ascii"))
    data.extend(b"trailer\n<< /Size 151 >>\nstartxref\n" + str(first).encode("ascii") + b"\n%%EOF\n")
    data[first:first + len(front)] = front.replace(b"0000000000 00000 n", f"{positions[1]:010d} 00000 n".encode("ascii"), 1).replace(
        b"0000000000 00000 n", f"{positions[2]:010d} 00000 n".encode("ascii"), 1).replace(
        b"/Prev 0000000000", f"/Prev {main:010d}".encode("ascii"))
    return bytes(data).replace(b"/L 0000000000", f"/L {len(data):010d}".encode("ascii")).replace(
        b"/E 0000000000", f"/E {main:010d}".encode("ascii")).replace(
        b"/T 0000000000", f"/T {main:010d}".encode("ascii"))


def cases():
    """name -> (metadata count, PDF bytes, expected count or refusal reason)."""
    return {
        "equal": ("7", classic(), 7),
        "different": ("8", classic(), 7),
        "incremental-equal": ("3", incremental(), 3),
        "incremental-different": ("2", incremental(), 3),
        "object-stream": ("7", compressed(), 7),
        "png-xref": ("7", compressed(predictor=True), 7),
        "encrypted": ("8", classic(encrypted=True), None),
        "pages-cycle": ("7", classic(cycle=True), "cycle"),
        "prev-cycle": ("7", prev_cycle(), "cycle"),
        "linearized": ("7", linearized(), 7),
        "portfolio": ("7", classic(portfolio=True), "portfolio"),
        "zero": ("7", classic(0, leaves=1), 0),
        "false-count": ("2", classic(5, leaves=2), 5),
        "long-number": ("9" * 4301, classic(), 7),
        "plus": ("+007", classic(), 7),
        "space": (" 7 ", classic(), 7),
        "invalid-zero": ("0", classic(), 7),
        "invalid-negative": ("-3", classic(), 7),
        "invalid-underscore": ("1_0", classic(), 7),
        "invalid-unicode": ("٧", classic(), 7),
        "window-limit": ("7", classic(padding=65536), "window"),
        "missing-startxref": ("7", classic().split(b"startxref")[0], "startxref"),
        "bad-xref": ("7", classic().replace(b"\nxref\n", b"\nxxxx\n"), "xref"),
        "real-count": ("7", classic("7.0", leaves=7), "integer"),
        "large-count": ("7", classic("9" * 4301, leaves=1), "range"),
        "object-stream-cycle": ("7", compressed(object_cycle=True), "cycle"),
        "compressed-claim": ("7", compressed(compressed_claim=True), 7),
        "multiple-pdfs": ("14", classic(), 7),
        "two-versions": ("8", classic(), 7),
        "unconfirmed": ("8", classic(unconfirmed=True), None),
        "overlapping-index": ("7", compressed(overlap=True), "Index"),
        "padded-pdf-count": ("7", classic("0" * 4301 + "7", leaves=7), 7),
        "hybrid-hidden": ("7", hybrid(), 7),
        "hybrid-conflict": ("7", hybrid(conflict=True), 7),
        "hybrid-pages-in-stream": ("7", hybrid(pages_in_stream=True), 7),
        "hybrid-in-prev": ("7", hybrid(conflict=True, previous=True), 7),
    }
