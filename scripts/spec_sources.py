"""Static, offline extraction of user-selected specifications."""

import hashlib
import os
import re
from html.parser import HTMLParser
from pathlib import Path


class SpecError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def line_locator(start, end):
    return f"L{start}" if start == end else f"L{start}-L{end}"


class Blocks:
    def __init__(self, source_id):
        self.source_id = source_id
        self.items = []
        self.headings = []
        self.warnings = []

    def add(self, kind, text, start, end, level=None, **extras):
        text = text.strip()
        if not text:
            return
        if level is not None:
            self.headings = self.headings[:level - 1]
            while len(self.headings) < level - 1:
                self.headings.append("")
            self.headings.append(text)
        block = {
            "id": f"{self.source_id}-B{len(self.items) + 1:04d}",
            "kind": kind,
            "locator": line_locator(start, end),
            "heading": [h for h in self.headings if h],
            "text": text,
        }
        block.update({k: v for k, v in extras.items() if v})
        self.items.append(block)

    def warn(self, message, line):
        self.warnings.append({"source_id": self.source_id, "locator": f"L{line}", "message": message})


def is_table_separator(line):
    if "|" not in line:
        return False
    cells = line.strip().strip("|").split("|")
    return bool(cells) and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells)


def markdown_blocks(text, source_id):
    result = Blocks(source_id)
    lines = text.splitlines()
    i = 0
    heading_re = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
    fence_re = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        heading = heading_re.match(lines[i])
        fence = fence_re.match(lines[i])
        if heading:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", heading[2])
            result.add("heading", title, i + 1, i + 1, level=len(heading[1]))
            i += 1
            continue
        if fence:
            i += 1
            closing = re.compile(r"^ {0,3}" + re.escape(fence[1][0]) + "{" + str(len(fence[1])) + r",}\s*$")
            while i < len(lines) and not closing.match(lines[i]):
                i += 1
            if i < len(lines):
                i += 1
            else:
                result.warn("Unclosed fenced code block; inspect the source.", start + 1)
            result.add("code", "\n".join(lines[start:i]), start + 1, i)
            continue
        if i + 1 < len(lines) and re.fullmatch(r" {0,3}(=+|-+)\s*", lines[i + 1]):
            level = 1 if lines[i + 1].lstrip().startswith("=") else 2
            result.add("heading", lines[i], i + 1, i + 2, level=level)
            i += 2
            continue
        table = i + 1 < len(lines) and is_table_separator(lines[i + 1])
        kind = "table" if table else ("list" if re.match(r"\s*(?:[-+*]|\d+[.)])\s+", lines[i]) else "paragraph")
        i += 1
        while i < len(lines) and lines[i].strip():
            if heading_re.match(lines[i]) or fence_re.match(lines[i]):
                break
            if not table and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
                break
            i += 1
        block_text = "\n".join(lines[start:i])
        result.add(kind, block_text, start + 1, i)
        if re.search(r"!\[|<\s*(?:img|svg|canvas)\b", block_text, re.I):
            result.warn("Visual material is referenced; inspect it before claiming coverage.", start + 1)
        if re.search(r"<\s*(?:script|iframe)\b", block_text, re.I):
            result.warn("Embedded active content is retained as text and was not executed.", start + 1)
    return result


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
IGNORED_TAGS = {"script", "style", "nav", "noscript", "template", "head"}
BLOCK_TAGS = {"p": "paragraph", "pre": "code", "table": "table", "ul": "list", "ol": "list", "blockquote": "quote", "svg": "diagram", "canvas": "diagram"}
BLOCK_TAGS.update({f"h{i}": "heading" for i in range(1, 7)})
BOUNDARIES = {"div", "section", "article", "main", "body", "header", "footer", "figure", "hr"}


def hidden(tag, attrs):
    attrs = dict(attrs)
    return (
        tag in IGNORED_TAGS or "hidden" in attrs
        or (attrs.get("aria-hidden") or "").lower() == "true"
        or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", attrs.get("style") or "", re.I))
        or "fl-badge" in (attrs.get("class") or "").split()
    )


class RootProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.roots = set()

    def handle_starttag(self, tag, attrs):
        skip = (self.stack[-1][1] if self.stack else False) or hidden(tag, attrs)
        if not skip and tag in {"article", "main", "body"}:
            self.roots.add(tag)
        if tag not in VOID_TAGS:
            self.stack.append((tag, skip))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


class HTMLBlocks(HTMLParser):
    def __init__(self, source_id, root):
        super().__init__(convert_charrefs=True)
        self.result = Blocks(source_id)
        self.root = root
        self.stack = []
        self.capture = None
        self.fallback = None

    def active(self):
        return (not self.stack or not self.stack[-1]["skip"]) and (
            self.root is None or any(frame["tag"] == self.root for frame in self.stack)
        )

    def current(self):
        if self.capture is not None:
            return self.capture
        if self.fallback is None:
            self.fallback = {"kind": "paragraph", "start": self.getpos()[0], "parts": [], "images": [], "links": []}
        return self.fallback

    def finish(self, which):
        block = getattr(self, which)
        if block is None:
            return
        text = "".join(block["parts"])
        if block["kind"] != "code":
            normalized = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                indent = len(line) - len(line.lstrip())
                value = " ".join(line.split())
                if block["kind"] == "list" and re.match(r"(?:-|\d+\.)\s", value):
                    value = " " * indent + value
                normalized.append(value)
            text = "\n".join(normalized)
        self.result.add(
            block["kind"], text, block["start"], self.getpos()[0],
            level=block.get("level"), images=block["images"], links=block["links"],
        )
        setattr(self, which, None)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        skip = (self.stack[-1]["skip"] if self.stack else False) or hidden(tag, attrs.items())
        if tag not in VOID_TAGS:
            self.stack.append({"tag": tag, "skip": skip, "items": 0})
        if skip or not self.active():
            return
        if tag in BLOCK_TAGS and self.capture is None:
            self.finish("fallback")
            self.capture = {
                "kind": BLOCK_TAGS[tag], "start": self.getpos()[0], "depth": len(self.stack),
                "parts": [], "images": [], "links": [],
            }
            if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
                self.capture["level"] = int(tag[1])
        elif tag in BOUNDARIES and self.capture is None:
            self.finish("fallback")
        if tag == "img":
            block = self.current()
            src = attrs.get("src") or ""
            alt = attrs.get("alt") or "无替代文字"
            block["parts"].append(f"[图片：{alt}]")
            block["images"].append({"src": "(embedded)" if src.startswith("data:") else src, "alt": alt})
            self.result.warn("Image text was not transcribed; inspect the original visual.", self.getpos()[0])
        elif tag in {"svg", "canvas"}:
            self.current()["parts"].append(f"[{tag}：需查看原文视觉内容]\n")
            self.result.warn("Diagram needs visual review; extracted text may be incomplete.", self.getpos()[0])
        elif tag in {"iframe", "object", "embed"}:
            self.current()["parts"].append(f"[{tag}：嵌入内容未加载]\n")
            reference = attrs.get("src") or attrs.get("data")
            if reference and not reference.startswith("data:"):
                self.current()["links"].append(reference)
            self.result.warn("Embedded content was not loaded; review a static local export.", self.getpos()[0])
        elif tag == "a" and attrs.get("href"):
            self.current()["links"].append(attrs["href"])
        elif tag == "br":
            self.current()["parts"].append("\n")
        elif tag == "li":
            parents = [frame for frame in self.stack if frame["tag"] in {"ul", "ol"}]
            if parents:
                parents[-1]["items"] += 1
                prefix = f"{parents[-1]['items']}." if parents[-1]["tag"] == "ol" else "-"
                self.current()["parts"].append("\n" + "  " * (len(parents) - 1) + prefix + " ")
        elif tag == "tr":
            self.current()["parts"].append("\n|")
        elif tag in {"td", "th"}:
            spans = [f"{key}={attrs[key]}" for key in ("rowspan", "colspan") if attrs.get(key, "1") != "1"]
            if spans:
                self.current()["parts"].append(" [" + ", ".join(spans) + "] ")
                self.result.warn("Merged table cells retain span markers; verify row and column relationships.", self.getpos()[0])
        elif tag == "p" and self.capture is not None and self.capture["depth"] < len(self.stack):
            parts = self.current()["parts"]
            if not parts or not re.search(r"(?:-|\d+\.)\s*$", parts[-1]):
                parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]["tag"] == tag), None)
        if index is None:
            return
        if self.active():
            if tag in {"td", "th"}:
                self.current()["parts"].append(" |")
            if self.capture is not None and self.capture["depth"] >= index + 1:
                self.finish("capture")
            if self.capture is None and tag in BOUNDARIES:
                self.finish("fallback")
        del self.stack[index:]

    def handle_data(self, data):
        if self.active() and (data.strip() or self.capture is not None):
            self.current()["parts"].append(data)

    def complete(self):
        self.finish("capture")
        self.finish("fallback")
        return self.result


def html_blocks(text, source_id):
    probe = RootProbe()
    probe.feed(text)
    root = next((tag for tag in ("article", "main", "body") if tag in probe.roots), None)
    parser = HTMLBlocks(source_id, root)
    parser.feed(text)
    parser.close()
    return parser.complete()


def extract_sources(paths, evidence_dir):
    result = {"schema_version": 1, "sources": [], "warnings": []}
    seen = set()
    for index, value in enumerate(paths, 1):
        path = Path(value).expanduser().resolve()
        if path in seen:
            raise SpecError(f"Duplicate input file: {path}")
        seen.add(path)
        suffix = path.suffix.lower()
        if suffix not in {".md", ".markdown", ".html", ".htm"}:
            raise SpecError(f"Unsupported input extension: {path.name}")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise SpecError(f"Input must be UTF-8: {path.name}") from error
        source_id = f"SRC-{index:03d}"
        is_html = suffix in {".html", ".htm"}
        blocks = html_blocks(text, source_id) if is_html else markdown_blocks(text, source_id)
        if not blocks.items:
            raise SpecError(f"No readable content in {path.name}; provide a static text export if the page requires JavaScript.")
        result["sources"].append({
            "id": source_id, "path": os.path.relpath(path, Path(evidence_dir).resolve()),
            "sha256": digest(raw), "format": "html" if is_html else "markdown", "blocks": blocks.items,
        })
        result["warnings"].extend(blocks.warnings)
    if not result["sources"]:
        raise SpecError("At least one source document is required.")
    return result
