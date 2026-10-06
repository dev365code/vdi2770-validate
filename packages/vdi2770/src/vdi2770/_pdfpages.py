"""Bounded access to a PDF's declared root Count; no recovery or leaf scan.

ISO 32000-1 §§7.5.4, 7.5.7, 7.5.8, 7.7.3.2 Table 29 and Annex F.
Sections retain bounded bytes, not a map of every object in an xref stream.
Only the at most sixteen objects this read asks for are interpreted.
"""
import re
import zlib
from dataclasses import dataclass

from . import pdfread

_WS = b"\x00\t\n\f\r "
_DELIMITERS = _WS + b"()<>[]{}/%"
_INTEGER = re.compile(rb"[+-]?[0-9]+")
_ROW = re.compile(rb"([0-9]{10}) ([0-9]{5}) ([nf])(?: \r| \n|\r\n)")


class Declined(ValueError):
    pass


class Name(str):
    pass


@dataclass(frozen=True)
class Ref:
    number: int
    generation: int


def uint(value, what, maximum=2**31 - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise Declined(f"{what} integer range or type")
    return value


class Syntax:
    """One bounded object window, with bounded nesting and integer conversion."""

    def __init__(self, data):
        self.data, self.pos = data, 0

    def skip(self):
        while self.pos < len(self.data):
            if self.data[self.pos] in _WS:
                self.pos += 1
            elif self.data[self.pos] == 37:
                while self.pos < len(self.data) and self.data[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                break

    def token(self):
        self.skip()
        at = self.pos
        if at >= len(self.data):
            raise Declined("object window exhausted or damaged syntax")
        pair = self.data[at:at + 2]
        if pair in (b"<<", b">>"):
            self.pos += 2
            return pair
        byte = self.data[at]
        if byte in b"[]":
            self.pos += 1
            return bytes([byte])
        if byte == 40:
            self.pos += 1
            depth = 1
            while self.pos < len(self.data) and depth:
                byte = self.data[self.pos]
                if byte == 92:
                    self.pos += 2
                    continue
                depth += (byte == 40) - (byte == 41)
                if depth > pdfread.MAX_PAGE_OBJECTS:
                    raise Declined("object syntax depth limit")
                self.pos += 1
            if depth:
                raise Declined("object window exhausted in string")
            return self.data[at:self.pos]
        if byte == 60:
            close = self.data.find(b">", at + 1)
            if close == -1:
                raise Declined("object window exhausted in hex string")
            self.pos = close + 1
            return self.data[at:self.pos]
        if byte == 47:
            self.pos += 1
            while self.pos < len(self.data) and self.data[self.pos] not in _DELIMITERS:
                self.pos += 1
            raw = re.sub(rb"#([0-9a-fA-F]{2})",
                         lambda m: bytes([int(m.group(1), 16)]), self.data[at + 1:self.pos])
            return Name(raw.decode("latin-1"))
        while self.pos < len(self.data) and self.data[self.pos] not in _DELIMITERS:
            self.pos += 1
        if self.pos == at:
            raise Declined("damaged object syntax")
        raw = self.data[at:self.pos]
        if _INTEGER.fullmatch(raw):
            # Decimal conversion is never handed an unbounded string.
            if len(raw.lstrip(b"+-")) > 10:
                raise Declined("integer range guard")
            value = int(raw)
            if not -(2**31) <= value < 2**31:
                raise Declined("integer range guard")
            return value
        return {b"true": True, b"false": False, b"null": None}.get(raw, raw)

    def value(self, depth=0):
        if depth >= pdfread.MAX_PAGE_OBJECTS:
            raise Declined("object syntax depth limit")
        item = self.token()
        if item == b"<<":
            out = {}
            while True:
                key = self.token()
                if key == b">>":
                    return out
                if not isinstance(key, Name) or key in out:
                    raise Declined("damaged or duplicate dictionary key")
                out[key] = self.value(depth + 1)
        if item == b"[":
            out = []
            while True:
                before = self.pos
                next_item = self.token()
                if next_item == b"]":
                    return out
                self.pos = before
                out.append(self.value(depth + 1))
        if type(item) is int:
            before = self.pos
            try:
                generation = self.token()
                if type(generation) is int and self.token() == b"R":
                    return Ref(uint(item, "object number"),
                               uint(generation, "generation", 65535))
            except Declined:
                pass
            self.pos = before
        return item


class PageReader:
    def __init__(self, data, allowance, file_left):
        self.data = data
        self.allowance = allowance
        self.file_left = file_left
        self.sections = []
        self.offsets = set()
        self.objects = 0
        self.cache = {}
        self.streams = {}
        self.active = set()

    def window(self, at):
        if not 0 < at < len(self.data):
            raise Declined("xref or object offset range")
        return self.data[at:at + pdfread.MAX_PAGE_OBJECT_WINDOW]

    def indirect_at(self, at, expected=None):
        if self.objects >= pdfread.MAX_PAGE_OBJECTS:
            raise Declined(f"object limit {pdfread.MAX_PAGE_OBJECTS}")
        self.objects += 1
        syntax = Syntax(self.window(at))
        number, generation, marker = syntax.token(), syntax.token(), syntax.token()
        reference = Ref(uint(number, "object number"), uint(generation, "generation", 65535))
        if marker != b"obj" or (expected is not None and reference != expected):
            raise Declined("xref does not point to the declared object header")
        value = syntax.value()
        end = syntax.token()
        if end == b"endobj":
            return value, None
        if end != b"stream" or not isinstance(value, dict):
            raise Declined("damaged object or object window limit")
        pos = syntax.pos
        if syntax.data[pos:pos + 2] == b"\r\n":
            pos += 2
        elif syntax.data[pos:pos + 1] in (b"\n", b"\r"):
            pos += 1
        else:
            raise Declined("damaged stream line ending")
        return value, at + pos

    def inflate(self, dictionary, at):
        length = uint(dictionary.get("Length"), "stream Length")
        if at + length > len(self.data):
            raise Declined("stream Length outside file")
        kind = dictionary.get("Filter")
        if isinstance(kind, list) and len(kind) == 1:
            kind = kind[0]
        if kind not in (None, Name("FlateDecode")):
            raise Declined("unsupported stream filter")
        if length > pdfread.MAX_STREAM_SCAN:
            raise Declined("compressed stream window limit")
        if kind is None:
            if length > pdfread.MAX_INFLATED_PER_STREAM:
                raise Declined("stream window limit")
            return self.data[at:at + length]
        file_cap = self.file_left[0]
        cap = min(pdfread.MAX_INFLATED_PER_STREAM, file_cap)
        if self.allowance is not None:
            cap = min(cap, self.allowance[0])
        reason = ("read inflation budget exhausted" if self.allowance is not None
                  and self.allowance[0] < file_cap
                  and self.allowance[0] <= pdfread.MAX_INFLATED_PER_STREAM
                  else "file inflation budget exhausted" if file_cap <= pdfread.MAX_INFLATED_PER_STREAM
                  else "stream inflation limit")
        if cap <= 0:
            raise Declined(reason)
        engine = zlib.decompressobj()
        try:
            out = engine.decompress(self.data[at:at + length], cap)
        except zlib.error as error:
            raise Declined("damaged Flate stream") from error
        self.file_left[0] -= len(out)
        if self.allowance is not None:
            self.allowance[0] -= len(out)
        if not engine.eof:
            raise Declined(reason)
        return self.predict(out, dictionary.get("DecodeParms"))

    def predict(self, data, parameters):
        if parameters is None:
            return data
        if isinstance(parameters, list) and len(parameters) == 1:
            parameters = parameters[0]
        if not isinstance(parameters, dict):
            raise Declined("unsupported predictor parameters")
        predictor = parameters.get("Predictor", 1)
        if predictor == 1:
            return data
        if predictor not in range(10, 16) or parameters.get("Colors", 1) != 1 \
                or parameters.get("BitsPerComponent", 8) != 8:
            raise Declined("unsupported stream predictor")
        width = uint(parameters.get("Columns", 1), "predictor Columns", pdfread.MAX_PAGE_OBJECT_WINDOW)
        if not width or len(data) % (width + 1):
            raise Declined("damaged predictor rows")
        previous = bytes(width)
        out = bytearray()
        for at in range(0, len(data), width + 1):
            kind = data[at]
            if kind > 4:
                raise Declined("unsupported PNG row predictor")
            row = bytearray(data[at + 1:at + width + 1])
            for i in range(width):
                left = row[i - 1] if i else 0
                up = previous[i]
                upper_left = previous[i - 1] if i else 0
                if kind == 1:
                    added = left
                elif kind == 2:
                    added = up
                elif kind == 3:
                    added = (left + up) // 2
                elif kind == 4:
                    base = left + up - upper_left
                    distances = (abs(base - left), abs(base - up), abs(base - upper_left))
                    added = (left, up, upper_left)[distances.index(min(distances))]
                else:
                    added = 0
                row[i] = (row[i] + added) % 256
            out.extend(row)
            previous = row
        return bytes(out)

    def section(self, at):
        if at in self.offsets:
            raise Declined("xref /Prev cycle")
        if len(self.offsets) >= pdfread.MAX_TRAILERS:
            raise Declined(f"xref section limit {pdfread.MAX_TRAILERS}")
        self.offsets.add(at)
        window = self.window(at)
        if window.startswith(b"xref"):
            syntax = Syntax(window)
            if syntax.token() != b"xref":
                raise Declined("damaged xref keyword")
            ranges = []
            while True:
                first = syntax.token()
                if first == b"trailer":
                    trailer = syntax.value()
                    if not isinstance(trailer, dict):
                        raise Declined("damaged xref trailer")
                    uint(trailer.get("Size"), "xref Size")
                    self.sections.append(("table", window, ranges))
                    return trailer
                first = uint(first, "xref first object")
                count = uint(syntax.token(), "xref subsection count")
                syntax.skip()
                start = syntax.pos
                stop = start + 20 * count
                if stop > len(window):
                    raise Declined("xref table window limit")
                ranges.append((first, count, start))
                syntax.pos = stop
        try:
            dictionary, stream_at = self.indirect_at(at)
        except Declined as error:
            raise Declined("xref: " + str(error)) from error
        if not isinstance(dictionary, dict) or dictionary.get("Type") != Name("XRef") or stream_at is None:
            raise Declined("damaged xref stream")
        widths = dictionary.get("W")
        if not isinstance(widths, list) or len(widths) != 3:
            raise Declined("damaged xref W")
        widths = [uint(n, "xref W", 8) for n in widths]
        if not sum(widths):
            raise Declined("xref W has no fields")
        size = uint(dictionary.get("Size"), "xref Size")
        index = dictionary.get("Index", [0, size])
        if not isinstance(index, list) or len(index) % 2:
            raise Declined("damaged xref Index")
        ranges, consumed = [], 0
        for i in range(0, len(index), 2):
            first = uint(index[i], "xref Index")
            count = uint(index[i + 1], "xref Index")
            if first + count > size:
                raise Declined("xref Index outside Size")
            ranges.append((first, count, consumed))
            consumed += count
        payload = self.inflate(dictionary, stream_at)
        if consumed * sum(widths) != len(payload):
            raise Declined("damaged xref stream length")
        self.sections.append(("stream", payload, ranges, widths))
        return dictionary

    def entry(self, reference):
        for section in self.sections:
            kind, data, ranges = section[:3]
            for first, count, at in ranges:
                if not first <= reference.number < first + count:
                    continue
                index = reference.number - first
                if kind == "table":
                    row = _ROW.fullmatch(data[at + 20 * index:at + 20 * (index + 1)])
                    if row is None:
                        raise Declined("damaged xref row")
                    offset, generation = int(row[1]), int(row[2])
                    if row[3] == b"f" or generation != reference.generation:
                        raise Declined("xref object is free or its generation changed")
                    return 1, offset, generation
                widths = section[3]
                start = (at + index) * sum(widths)
                fields = []
                for i, width in enumerate(widths):
                    fields.append(int.from_bytes(data[start:start + width], "big")
                                  if width else 1 if i == 0 else 0)
                    start += width
                if fields[0] == 0 or (fields[0] == 1 and fields[2] != reference.generation):
                    raise Declined("xref object is free or its generation changed")
                if fields[0] == 2 and reference.generation != 0:
                    raise Declined("compressed object generation is not zero")
                return tuple(fields)
        raise Declined("object is absent from xref")

    def object(self, reference):
        if reference in self.cache:
            return self.cache[reference]
        if reference in self.active:
            raise Declined("object stream reference cycle")
        self.active.add(reference)
        try:
            return self.interpret(reference)
        finally:
            self.active.remove(reference)

    def interpret(self, reference):
        kind, at, index = self.entry(reference)
        if kind == 1:
            result = self.indirect_at(at, reference)
        elif kind == 2:
            if at not in self.streams:
                dictionary, stream_at = self.object(Ref(uint(at, "object stream number"), 0))
                if not isinstance(dictionary, dict) or dictionary.get("Type") != Name("ObjStm") or stream_at is None:
                    raise Declined("xref does not name an object stream")
                payload = self.inflate(dictionary, stream_at)
                first = uint(dictionary.get("First"), "object stream First")
                count = uint(dictionary.get("N"), "object stream N")
                if first > len(payload):
                    raise Declined("object stream header range")
                # Only the bounded header is parsed, never each object's body.
                if first > pdfread.MAX_PAGE_OBJECT_WINDOW:
                    raise Declined("object stream header window limit")
                syntax = Syntax(payload[:first])
                entries = []
                for _ in range(count):
                    number = uint(syntax.token(), "object stream number")
                    offset = uint(syntax.token(), "object stream offset")
                    if offset + first >= len(payload) or (entries and offset <= entries[-1][1]):
                        raise Declined("object stream offset range or order")
                    entries.append((number, offset))
                syntax.skip()
                if syntax.pos != first:
                    raise Declined("object stream header length")
                self.streams[at] = (payload, first, entries)
            payload, first, entries = self.streams[at]
            if not 0 <= index < len(entries) or entries[index][0] != reference.number:
                raise Declined("object stream index or number")
            if self.objects >= pdfread.MAX_PAGE_OBJECTS:
                raise Declined(f"object limit {pdfread.MAX_PAGE_OBJECTS}")
            self.objects += 1
            start = first + entries[index][1]
            end = first + entries[index + 1][1] if index + 1 < len(entries) else len(payload)
            if end - start > pdfread.MAX_PAGE_OBJECT_WINDOW:
                raise Declined("object stream object window limit")
            syntax = Syntax(payload[start:end])
            value = syntax.value()
            syntax.skip()
            if syntax.pos != end - start:
                raise Declined("damaged compressed object")
            result = value, None
        else:
            raise Declined("unsupported xref entry type")
        self.cache[reference] = result
        return result

    def resolve(self, value, visited):
        while isinstance(value, Ref):
            if value in visited:
                raise Declined("page tree object reference cycle")
            visited.add(value)
            value, _ = self.object(value)
        return value

    def count(self):
        at = self.data.rfind(b"startxref")
        if at == -1:
            raise Declined("startxref is missing")
        hit = pdfread._STARTXREF.match(self.data, at)
        if hit is None:
            raise Declined("startxref integer range or syntax")
        offset = int(hit[1])
        absent = object()
        root = absent
        while offset:
            trailer = self.section(offset)
            if root is absent and "Root" in trailer:
                root = trailer["Root"]
            # Hybrid-reference streams supersede this table's entries.
            extra = trailer.get("XRefStm")
            if extra is not None:
                table = self.sections.pop()
                self.section(uint(extra, "XRefStm offset", len(self.data) - 1))
                self.sections.append(table)
            offset = uint(trailer.get("Prev", 0), "Prev offset", len(self.data) - 1)
        if not isinstance(root, Ref):
            raise Declined("trailer Root is not an indirect reference")
        visited = set()
        catalog = self.resolve(root, visited)
        if not isinstance(catalog, dict) or catalog.get("Type") != Name("Catalog"):
            raise Declined("Root is not a catalog")
        if "Collection" in catalog:
            raise Declined("portfolio")
        pages = self.resolve(catalog.get("Pages"), visited)
        if not isinstance(pages, dict) or pages.get("Type") != Name("Pages"):
            raise Declined("catalog Pages is not a page tree")
        count = self.resolve(pages.get("Count"), visited)
        return uint(count, "page tree Count")


def declared_count(data, allowance, file_left):
    try:
        return PageReader(data, allowance, file_left).count(), None
    except Declined as error:
        return None, str(error)
