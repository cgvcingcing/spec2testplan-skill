#!/usr/bin/env python3
"""Offline helpers for the spec2testplan agent skill; no model calls."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

from spec_plan import load_evidence, read_json, render_plan, validate_plan
from spec_sources import SpecError, extract_sources


def write_output(path, content, protected=()):
    output = Path(path).expanduser().resolve()
    if output in {Path(p).expanduser().resolve() for p in protected}:
        raise SpecError("Output would overwrite an input or evidence file")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, prefix=".spec2testplan-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="spec2testplan 1.3.0")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Extract source blocks without executing document content")
    extract.add_argument("inputs", nargs="+")
    extract.add_argument("-o", "--output", required=True)
    for name in ("validate", "render"):
        command = commands.add_parser(name, help="Render an intermediate Markdown document" if name == "render" else "Validate an internal design")
        command.add_argument("plan", help="Agent-authored testplan.json")
        command.add_argument("--sources", required=True, help="Original sources.json from extract")
        if name == "render":
            command.add_argument("-o", "--output", required=True)
            command.add_argument("--document-dir", help="Final delivery directory used for source paths; defaults to the Markdown output directory")
            command.add_argument("--layout", choices=("html", "markdown"), default="html", help="HTML-ready reading layers (default) or portable Markdown")
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            evidence = extract_sources(args.inputs, Path(args.output).expanduser().resolve().parent)
            write_output(args.output, json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", args.inputs)
            count = sum(len(s["blocks"]) for s in evidence["sources"])
            print(f"Extracted {len(evidence['sources'])} source(s), {count} block(s), {len(evidence['warnings'])} warning(s): {Path(args.output).resolve()}")
        else:
            evidence = load_evidence(args.sources)
            plan = read_json(args.plan)
            stats = validate_plan(plan, evidence)
            if args.command == "render":
                originals = [Path(args.sources).resolve().parent / source["path"] for source in evidence["sources"]]
                document_dir = Path(args.document_dir or Path(args.output).expanduser().resolve().parent).expanduser().resolve()
                document = render_plan(plan, evidence, Path(args.sources).resolve().parent, document_dir, args.layout)
                write_output(args.output, document, [args.plan, args.sources] + originals)
                print(f"Rendered: {Path(args.output).resolve()}")
            print("Validation OK: " + ", ".join(f"{key}={value}" for key, value in stats.items()))
        return 0
    except (SpecError, OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
