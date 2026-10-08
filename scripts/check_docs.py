#!/usr/bin/env python3
"""ドキュメントと設定ファイルの整合を検査する（ネットワークを使わない）.

- Markdown の相対リンク（ファイル・フォルダ・見出しアンカー）がリポジトリ内で解決できる
- context-sources.yaml が参照するフォルダ・テンプレートが実在する
- YAML / JSON ファイルが構文として読める
- Copilot のプロンプト・指示ファイルの Front Matter が読め、必須キーがある
- Copilot のファイル（エージェント・プロンプト・指示）のコマンドに `&&` が無い（Windows PowerShell 5.1 で動かない）

対象は git 管理下のファイル（git が使えないときはフォルダを走査）。
終了コード: 0 問題なし / 1 問題あり
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "build", ".gradle", "node_modules", ".venv", "__pycache__", ".ruff_cache", "out"}

# Copilot のカスタマイズファイルごとの必須キー
FRONTMATTER_RULES: list[tuple[str, tuple[str, ...]]] = [
    (".instructions.md", ("applyTo",)),
    (".prompt.md", ("description",)),
    (".agent.md", ("description",)),
    ("/SKILL.md", ("name", "description")),
]

FENCE = re.compile(r"^\s{0,3}(```|~~~)")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
# [text](target "title") と ![alt](target)。target は <...> 囲みも許す
INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
HTML_ANCHOR = re.compile(r"<a\s+[^>]*(?:id|name)=[\"']([^\"']+)[\"']", re.I)
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
EXTERNAL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def repo_files(root: Path) -> list[Path]:
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        if Path(top).resolve() != root.resolve():
            raise OSError("not the repository root")
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True, text=True).stdout
        files = [root / p for p in out.split("\0") if p]
        return [p for p in files if p.is_file()]
    except (OSError, subprocess.CalledProcessError):
        return [
            p
            for p in root.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
        ]


def strip_code(text: str) -> list[str]:
    """コードブロックを空行に、インラインコードを空白に置き換えた行のリスト."""
    lines, in_fence, marker = [], False, ""
    for line in text.splitlines():
        m = FENCE.match(line)
        if m and (not in_fence or m.group(1) == marker):
            in_fence, marker = not in_fence, m.group(1)
            lines.append("")
            continue
        lines.append("" if in_fence else INLINE_CODE.sub(lambda x: " " * len(x.group(0)), line))
    return lines


def slugify(heading: str) -> str:
    """GitHub の見出しアンカーと同じ規則で slug を作る."""
    s = re.sub(r"<[^>]+>", "", heading)
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)  # リンクは文字だけ残す
    s = s.replace("`", "").lower()
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if ch in "-_" or cat[0] in ("L", "N") or cat == "Mn" or cat == "Mc":
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)


def anchors(md: Path, cache: dict[Path, set[str]]) -> set[str]:
    if md not in cache:
        found: set[str] = set()
        counts: dict[str, int] = {}
        for line in strip_code(md.read_text(encoding="utf-8")):
            found.update(HTML_ANCHOR.findall(line))
            m = HEADING.match(line)
            if not m:
                continue
            slug = slugify(m.group(2))
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            found.add(slug if n == 0 else f"{slug}-{n}")
        cache[md] = found
    return cache[md]


def check_links(root: Path, files: list[Path]) -> list[str]:
    errs: list[str] = []
    cache: dict[Path, set[str]] = {}
    for md in (p for p in files if p.suffix.lower() == ".md"):
        rel = md.relative_to(root).as_posix()
        text = md.read_text(encoding="utf-8")
        # Front Matter はリンクを持たない
        body = re.sub(r"\A---\n.*?\n---\n", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        for no, line in enumerate(strip_code(body), 1):
            targets = [m.group(1) for m in INLINE_LINK.finditer(line)]
            targets += [m.group(1) for m in REF_DEF.finditer(line)]
            for raw in targets:
                target = raw.strip("<>")
                if not target or EXTERNAL.match(target) or target.startswith("//"):
                    continue
                path_part, _, frag = target.partition("#")
                path_part = unquote(path_part.split("?", 1)[0])
                if path_part.startswith("/"):
                    dest = root / path_part.lstrip("/")
                elif path_part:
                    dest = md.parent / path_part
                else:
                    dest = md
                where = f"{rel}:{no}"
                try:
                    dest.resolve().relative_to(root.resolve())
                except ValueError:
                    errs.append(f"{where}: リポジトリの外を指している: {target}")
                    continue
                if not dest.exists():
                    errs.append(f"{where}: リンク先がない: {target}")
                    continue
                if (
                    frag
                    and dest.is_file()
                    and dest.suffix.lower() == ".md"
                    and unquote(frag).lower() not in anchors(dest, cache)
                ):
                    errs.append(f"{where}: 見出しアンカーがない: {target}")
    return errs


def check_context_sources(root: Path) -> list[str]:
    cfg = root / "context-sources.yaml"
    if not cfg.exists():
        return []
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return [f"context-sources.yaml: YAML として読めない: {e}"]
    errs: list[str] = []
    for i, r in enumerate(data.get("roots") or []):
        p = (r or {}).get("path")
        if not p:
            errs.append(f"context-sources.yaml: roots[{i}] に path がない")
        elif not (root / p).is_dir():
            errs.append(f"context-sources.yaml: roots[{i}].path のフォルダがない: {p}")
    for name, t in (data.get("types") or {}).items():
        tpl = (t or {}).get("template")
        if tpl and not (root / tpl).is_file():
            errs.append(f"context-sources.yaml: types.{name}.template のファイルがない: {tpl}")
    return errs


def check_parse(root: Path, files: list[Path]) -> list[str]:
    errs: list[str] = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        suffix = p.suffix.lower()
        try:
            if suffix in (".yml", ".yaml"):
                list(yaml.safe_load_all(p.read_text(encoding="utf-8")))
            elif suffix == ".json":
                json.loads(p.read_text(encoding="utf-8"))
        except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError) as e:
            first = str(e).splitlines()[0] if str(e) else type(e).__name__
            kind = "JSON" if suffix == ".json" else "YAML"
            errs.append(f"{rel}: {kind} として読めない: {first}")
    return errs


def front_matter(text: str) -> dict | None:
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    data = yaml.safe_load(m.group(1))
    return data if isinstance(data, dict) else {}


def check_copilot(root: Path, files: list[Path]) -> list[str]:
    errs: list[str] = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        required = next((keys for suffix, keys in FRONTMATTER_RULES if ("/" + rel).endswith(suffix)), None)
        if required is None:
            continue
        try:
            fm = front_matter(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errs.append(f"{rel}: Front Matter が YAML として読めない: {str(e).splitlines()[0]}")
            continue
        if fm is None:
            errs.append(f"{rel}: Front Matter（--- で囲んだ先頭部分）がない")
            continue
        for key in required:
            v = fm.get(key)
            if v is None or (isinstance(v, str) and not v.strip()):
                errs.append(f"{rel}: Front Matter に {key} がない")
        if rel.endswith("/SKILL.md") and fm.get("name") and fm["name"] != p.parent.name:
            errs.append(f"{rel}: name（{fm['name']}）がフォルダ名（{p.parent.name}）と違う")
    return errs


def is_copilot_file(rel: str) -> bool:
    return rel == ".github/copilot-instructions.md" or any(("/" + rel).endswith(sfx) for sfx, _ in FRONTMATTER_RULES)


def check_commands(root: Path, files: list[Path]) -> list[str]:
    """エージェントが実行するコマンドに && が無いか（Windows PowerShell 5.1 は && を解釈できない）.

    コード（インラインと囲み）の中だけを見る. `&&` 単独（説明のための記号）は対象外.
    """
    errs: list[str] = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        if not is_copilot_file(rel):
            continue
        in_fence = False
        for no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            codes = [line] if in_fence else [m.group(0).strip("`") for m in INLINE_CODE.finditer(line)]
            if any("&&" in c and c.strip() != "&&" for c in codes):
                errs.append(
                    f"{rel}:{no}: コマンドに && がある（Windows PowerShell 5.1 で動かない。1 つずつ実行するか、"
                    "Gradle は -p template で指定する）"
                )
    return errs


def verify(root: Path) -> list[str]:
    files = repo_files(root)
    return (
        check_links(root, files)
        + check_context_sources(root)
        + check_parse(root, files)
        + check_copilot(root, files)
        + check_commands(root, files)
    )


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    errs = verify(root)
    for e in errs:
        print(f"::error::{e}" if "GITHUB_ACTIONS" in os.environ else e)
    print(f"check_docs: {'NG ' + str(len(errs)) + ' 件' if errs else 'OK'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
