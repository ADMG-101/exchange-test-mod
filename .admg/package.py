#!/usr/bin/env python3
"""ADMG Exchange publisher tool: personalize a new repository, check it, and build release packages.

Python 3.10+ standard library only, so it runs unchanged on GitHub's runners and on your own machine.

  python3 .admg/package.py personalize --owner OWNER --repo REPO   (run once by the setup workflow)
  python3 .admg/package.py check                                   (what the check workflow runs)
  python3 .admg/package.py sync                                    (modpacks: write modpack/modpack.json from the pins)
  python3 .admg/package.py build --version 1.2.3 --out dist        (what the release workflow runs)

Packages are deterministic: the same files give the same bytes (sorted entries, fixed timestamps and permissions).
Every packaged file is a committed file, unchanged, so Exchange can match the package to the tagged commit.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTOR = ROOT / ".admg" / "exchange.json"
PLACEHOLDERS = ("__OWNER__", "__PUBLISHER__", "__REPO__", "__NAME__", "__YEAR__")
PERSONALIZED = (".admg/exchange.json", "mod/mod.json", "LICENSE", "README.md")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)

# Accepted open-source licences (SPDX). Exchange checks the same list and GitHub's licence detection at your tag.
OPEN_SOURCE = {
    "0BSD", "AFL-3.0", "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later", "Apache-2.0", "Artistic-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "BSL-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "ECL-2.0", "EPL-2.0", "EUPL-1.2", "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later",
    "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "ISC", "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0", "LGPL-3.0-only",
    "LGPL-3.0-or-later", "MIT", "MIT-0", "MPL-2.0", "MS-PL", "NCSA", "OFL-1.1", "PostgreSQL", "UPL-1.0", "Unlicense", "Zlib",
}
PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}\.[a-z0-9][a-z0-9-]{0,63}$")
MOD_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MODPACK_FILES = {".json", ".md", ".txt", ".png"}


class Problem(Exception):
    def __init__(self, message: str, file: str | None = None):
        super().__init__(message)
        self.file = file


def report(problems: list[Problem]) -> int:
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for p in problems:
        if in_actions:
            print(f"::error{' file=' + p.file if p.file else ''}::{p}")
        else:
            print(f"error: {p.file + ': ' if p.file else ''}{p}", file=sys.stderr)
    return 1 if problems else 0


def segment(text: str) -> str:
    """An id segment from a GitHub name: lowercase, anything else becomes '-'."""
    value = re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-") or "mod"
    return value


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Problem("missing", str(path.relative_to(ROOT)))
    except json.JSONDecodeError as error:
        raise Problem(f"not valid JSON: {error}", str(path.relative_to(ROOT)))


# ---------------------------------------------------------------- personalize

def personalize(owner: str, repo: str) -> None:
    values = {
        "__OWNER__": owner,
        "__PUBLISHER__": segment(owner)[:32],
        "__REPO__": repo,
        "__NAME__": segment(repo)[:64],
        "__YEAR__": str(datetime.date.today().year),
    }
    changed = []
    for relative in PERSONALIZED:
        path = ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for key, value in values.items():
            new = new.replace(key, value)
        if new != text:
            path.write_text(new, encoding="utf-8", newline="\n")
            changed.append(relative)
    print("personalized: " + (", ".join(changed) if changed else "nothing to change"))


# ---------------------------------------------------------------- check

def check() -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    rel = ".admg/exchange.json"
    try:
        descriptor = load_json(DESCRIPTOR)
    except Problem as p:
        return {}, [p]
    if any(marker in json.dumps(descriptor) for marker in PLACEHOLDERS):
        return descriptor, [Problem("still has template placeholders: wait for the setup workflow's commit, or run "
                                    "'python3 .admg/package.py personalize --owner <owner> --repo <repo>'", rel)]
    if descriptor.get("schema") != 1:
        problems.append(Problem('"schema" must be 1', rel))
    project = descriptor.get("project") or {}
    project_id = project.get("id", "")
    if not PROJECT_ID.match(project_id):
        problems.append(Problem(f"project.id '{project_id}' must look like '<your-github-name>.<project-name>' (lowercase letters, digits, '-')", rel))
    kind = project.get("type")
    if kind not in ("mod", "modpack"):
        problems.append(Problem("project.type must be 'mod' or 'modpack'", rel))
    licence = (project.get("license") or {}).get("name")
    if not licence:
        problems.append(Problem("declare your open-source licence: project.license.name is its SPDX identifier, e.g. \"MIT\"", rel))
    elif licence not in OPEN_SOURCE:
        problems.append(Problem(f"'{licence}' is not an accepted open-source licence (use an SPDX id such as MIT, Apache-2.0, GPL-3.0-or-later, CC-BY-4.0)", rel))
    licence_file = (project.get("license") or {}).get("file", "LICENSE")
    if not (ROOT / licence_file).is_file():
        problems.append(Problem(f"the licence text must be in {licence_file}", licence_file))
    artifacts = (descriptor.get("release") or {}).get("artifacts") or []
    if not artifacts:
        problems.append(Problem("release.artifacts must name the release asset", rel))
    if kind == "mod":
        for package in (descriptor.get("mod") or {}).get("packages") or []:
            manifest_path = ROOT / "mod" / "mod.json"
            try:
                manifest = load_json(manifest_path)
            except Problem as p:
                problems.append(p)
                continue
            mref = str(manifest_path.relative_to(ROOT))
            if manifest.get("id") != package.get("modId"):
                problems.append(Problem(f"mod.json id '{manifest.get('id')}' differs from the descriptor's modId '{package.get('modId')}'", mref))
            if manifest.get("game_id") != package.get("gameId"):
                problems.append(Problem(f"mod.json game_id '{manifest.get('game_id')}' differs from the descriptor's gameId '{package.get('gameId')}'", mref))
            if not MOD_ID.match(str(manifest.get("id", ""))):
                problems.append(Problem("mod.json id must be lowercase letters, digits, '.', '_' or '-'", mref))
            if not VERSION.match(str(manifest.get("version", ""))):
                problems.append(Problem("mod.json version must be a semantic version like 1.0.0", mref))
            if "{version}" not in package.get("asset", ""):
                problems.append(Problem("the package asset name should contain {version}, e.g. my-mod-{version}.zip", rel))
    elif kind == "modpack":
        pack = descriptor.get("modpack") or {}
        if pack.get("seal") not in ("sealed", "sealed+", "open"):
            problems.append(Problem("modpack.seal must be 'sealed', 'sealed+' or 'open'", rel))
        members = pack.get("members") or []
        if not members:
            problems.append(Problem("modpack.members must pin at least one approved mod release", rel))
        for i, member in enumerate(members):
            if member.get("project") == "publisher.member-mod" or set(str(member.get("sha256", ""))) == {"0"}:
                problems.append(Problem(f"members[{i}] is the template's example: pin a real approved release (project, release, modId and sha256 from its ADMG Exchange page)", rel))
                continue
            if not SHA256.match(str(member.get("sha256", ""))):
                problems.append(Problem(f"members[{i}].sha256 must be the approved package's SHA-256 (64 lowercase hex digits) from its Exchange page", rel))
            if not str(member.get("release", "")).startswith(str(member.get("project", "?")) + "@"):
                problems.append(Problem(f"members[{i}].release must be '<project>@<version>'", rel))
            for key, value in (member.get("options") or {}).items():
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    problems.append(Problem(f"members[{i}].options.{key} must be text or a number (the runtime has no true/false setting)", rel))
        manifest = ROOT / "modpack" / "modpack.json"
        if not problems and (not manifest.is_file() or manifest.read_bytes().replace(b"\r\n", b"\n") != modpack_manifest(descriptor)):
            problems.append(Problem("modpack/modpack.json is missing or differs from the pins in .admg/exchange.json: "
                                    "run 'python3 .admg/package.py sync' and commit the result", "modpack/modpack.json"))
    return descriptor, problems


def modpack_manifest(descriptor: dict) -> bytes:
    """modpack.json as the release ships it: exactly the descriptor's game, seal and pinned members."""
    pack = descriptor.get("modpack") or {}
    manifest = {"gameId": pack.get("gameId"), "seal": pack.get("seal"), "members": pack.get("members")}
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sync() -> None:
    descriptor = load_json(DESCRIPTOR)
    if (descriptor.get("project") or {}).get("type") != "modpack":
        raise Problem("sync is for modpacks", ".admg/exchange.json")
    target = ROOT / "modpack" / "modpack.json"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(modpack_manifest(descriptor))
    print("wrote modpack/modpack.json")


# ---------------------------------------------------------------- build

def deterministic_zip(target: Path, files: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, data)


def folder_files(folder: Path) -> list[tuple[str, bytes]]:
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            if any(part.startswith(".") for part in relative.split("/")):
                continue
            files.append((relative, path.read_bytes()))
    return files


def build(version: str, out: Path) -> list[Path]:
    if not VERSION.match(version):
        raise Problem(f"'{version}' is not a semantic version; tag releases like v1.2.3")
    descriptor, problems = check()
    if problems:
        raise SystemExit(report(problems))
    out.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []
    kind = descriptor["project"]["type"]
    if kind == "mod":
        for package in descriptor["mod"]["packages"]:
            folder = ROOT / "mod"
            manifest = load_json(folder / "mod.json")
            if manifest.get("version") != version:
                raise SystemExit(report([Problem(f"mod.json version is {manifest.get('version')}, but the tag is v{version}: "
                                                 "set the version in mod.json, commit, and tag that commit", str((folder / 'mod.json').relative_to(ROOT)))]))
            files = folder_files(folder)
            if any(name.endswith((".gba", ".elf", ".bps", ".ips", ".ups")) for name, _ in files):
                raise SystemExit(report([Problem("packages may not contain game ROMs or ROM patches", str(folder.relative_to(ROOT)))]))
            target = out / package["asset"].replace("{version}", version)
            deterministic_zip(target, files)
            built.append(target)
    else:
        pack = descriptor["modpack"]
        files = folder_files(ROOT / "modpack")
        for name, _ in files:
            if Path(name).suffix.lower() not in MODPACK_FILES:
                raise SystemExit(report([Problem(f"modpack/{name}: a modpack may hold only {', '.join(sorted(MODPACK_FILES))} files")]))
        target = out / pack["asset"].replace("{version}", version)
        deterministic_zip(target, files)
        built.append(target)
    sums = out / "SHA256SUMS"
    with sums.open("w", encoding="utf-8", newline="\n") as handle:
        for path in built:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            handle.write(f"{digest}  {path.name}\n")
            print(f"{path.name}  {path.stat().st_size} bytes  sha256 {digest}")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("personalize")
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    sub.add_parser("check")
    sub.add_parser("sync")
    b = sub.add_parser("build")
    b.add_argument("--version", required=True)
    b.add_argument("--out", default="dist")
    args = parser.parse_args()
    try:
        if args.command == "personalize":
            personalize(args.owner, args.repo)
            return 0
        if args.command == "sync":
            sync()
            return 0
        if args.command == "check":
            _, problems = check()
            if not problems:
                print("ok: ready to release")
            return report(problems)
        build(args.version, Path(args.out))
        return 0
    except Problem as problem:
        return report([problem])


if __name__ == "__main__":
    sys.exit(main())
