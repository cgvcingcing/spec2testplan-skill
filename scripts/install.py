#!/usr/bin/env python3
"""Install the same native skill in Codex and Claude Code."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path


NAME = "spec2testplan"
VERSION = "1.2.0"
MARKER = ".spec2testplan-install.json"
PROJECT = Path(__file__).resolve().parent.parent
PAYLOAD = (
    "SKILL.md", "agents/openai.yaml", "references/output-contract.md",
    "scripts/spec2testplan.py", "scripts/spec_sources.py", "scripts/spec_plan.py",
)


def payload_hashes():
    return {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in PAYLOAD}


def managed(destination):
    if destination.is_symlink():
        raise ValueError(f"Refusing to replace a symlink: {destination}")
    if not destination.exists():
        return False
    marker = destination / MARKER
    if not destination.is_dir() or not marker.is_file():
        raise ValueError(f"Existing directory is not managed by this installer: {destination}")
    record = json.loads(marker.read_text(encoding="utf-8"))
    if record.get("name") != NAME:
        raise ValueError(f"Installation marker does not belong to {NAME}: {destination}")
    return True


def check_install(destination, hashes):
    if not managed(destination):
        raise ValueError(f"Skill is not installed: {destination}")
    record = json.loads((destination / MARKER).read_text(encoding="utf-8"))
    if record.get("version") != VERSION or record.get("files") != hashes:
        raise ValueError(f"Installation differs from this project version: {destination}")
    for name, expected in hashes.items():
        installed = destination / name
        if installed.is_symlink() or not installed.is_file() or hashlib.sha256(installed.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Missing or modified installed file: {installed}")


def install(destination, hashes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{NAME}-stage-", dir=destination.parent))
    backup = destination.with_name(f".{NAME}-backup-{uuid.uuid4().hex}")
    previous = False
    try:
        for name in PAYLOAD:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / name, target)
        record = {"name": NAME, "version": VERSION, "files": hashes}
        (staging / MARKER).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            os.replace(destination, backup)
            previous = True
        try:
            os.replace(staging, destination)
        except OSError:
            if previous:
                os.replace(backup, destination)
            raise
        if previous:
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    check_install(destination, hashes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("all", "codex", "claude"), default="all")
    parser.add_argument("--codex-root", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--claude-root", default=os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--uninstall", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        roots = {"codex": args.codex_root, "claude": args.claude_root}
        targets = ["codex", "claude"] if args.target == "all" else [args.target]
        destinations = []
        for target in targets:
            destination = Path(roots[target]).expanduser().absolute() / "skills" / NAME
            if destination.resolve() == PROJECT or destination.resolve() in PROJECT.parents:
                raise ValueError("Installation destination would replace the source project")
            managed(destination)  # Check every destination before any changes.
            if destination not in destinations:
                destinations.append(destination)
        hashes = payload_hashes() if not args.uninstall else None
        for destination in destinations:
            if args.uninstall:
                if managed(destination):
                    shutil.rmtree(destination)
                    print(f"Uninstalled: {destination}")
                else:
                    print(f"Already absent: {destination}")
            elif args.check:
                check_install(destination, hashes)
                print(f"Verified {VERSION}: {destination}")
            else:
                install(destination, hashes)
                print(f"Installed {VERSION}: {destination}")
        return 0
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
