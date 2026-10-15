"""Validate and reproducibly package the skill using Python's standard library."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "patent-oa-response"
ROOT_FILES = (
    "SKILL.md", "LICENSE", "README.md", "KNOWN_ISSUES.md", "CHANGELOG.md",
    "CONTRIBUTING.md", "DEPLOY.md", "VERSION", "UPSTREAM.json", "scripts/package_skill.py",
)


def package_files() -> list[Path]:
    paths = [ROOT / name for name in ROOT_FILES]
    for folder in ("references", "assets"):
        paths.extend(sorted((ROOT / folder).rglob("*.md")))
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def validate() -> tuple[str, list[Path]]:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version):
        raise ValueError("VERSION must be a semantic version")
    files = package_files()
    for path in files:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Missing or unsafe package file: {path.name}")
        if not path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Empty package file: {path.name}")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", skill, re.S)
    if not match:
        raise ValueError("SKILL.md requires YAML frontmatter")
    metadata = dict(re.findall(r"^([a-z-]+):\s*(.+)$", match.group(1), re.M))
    if metadata.get("name") != NAME or not metadata.get("description"):
        raise ValueError("Unexpected skill name or empty description")
    if len(metadata["description"]) > 1024:
        raise ValueError("Skill description exceeds 1024 characters")
    included = {path.resolve() for path in files}
    for path in files:
        if path.suffix != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = (path.parent / target.split("#", 1)[0]).resolve()
            if local not in included:
                raise ValueError(f"Unpackaged link in {path.name}: {target}")
    return version, files


def build(output_dir: Path) -> None:
    version, files = validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_path = output_dir / f"{NAME}-{version}.skill"
    with zipfile.ZipFile(skill_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            entry = zipfile.ZipInfo(f"{NAME}/{path.relative_to(ROOT).as_posix()}", (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    with zipfile.ZipFile(skill_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed")
        for path in files:
            name = f"{NAME}/{path.relative_to(ROOT).as_posix()}"
            if archive.read(name) != path.read_bytes():
                raise ValueError(f"Packaged content mismatch: {name}")
    zip_path = skill_path.with_suffix(".zip")
    zip_path.write_bytes(skill_path.read_bytes())
    checksum = hashlib.sha256(skill_path.read_bytes()).hexdigest()
    (output_dir / "SHA256SUMS.txt").write_text(
        f"{checksum}  {skill_path.name}\n{checksum}  {zip_path.name}\n", encoding="utf-8"
    )
    print(f"Built {skill_path.name} and {zip_path.name}; {len(files)} files; SHA256 {checksum}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--build", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        if args.build:
            build(args.out_dir)
        else:
            version, files = validate()
            print(f"Valid skill {NAME} v{version}: {len(files)} packaged files and local links verified")
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
