#!/usr/bin/env python3
"""権限のグラフ（traceability/authority.yaml）を検証する（品質ゲート D11）.

- check が参照する rule が存在する（存在しない根拠で検査しない）
- enforcement: machine の rule に、少なくとも 1 つ check がある（ルールが空文化していない）
- rule の source（ガイドラインのファイルと見出し）が実在する
- check の ID が guidelines/quality-gates.md の表にある
- check の実体（Gradle のタスク名・ツール名）が実在する

終了コード: 0 問題なし / 1 問題あり
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# Gradle のプラグインが提供するタスク（値はプラグイン ID。java は常にある）
PLUGIN_TASKS = {
    "compileJava": None,
    "test": None,
    "checkstyleMain": "checkstyle",
    "jacocoTestCoverageVerification": "jacoco",
    "spotbugsMain": "com.github.spotbugs",
}
TOOLS = {
    "spec-trace": "tools/spec-trace",
    "verify_authority.py": "scripts/verify_authority.py",
    "reviewer": ".github/agents/reviewer.agent.md",
}


def headings(md: Path) -> set[str]:
    return {m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.+)$", md.read_text(encoding="utf-8"), re.M)}


def verify(root: Path) -> list[str]:
    data = yaml.safe_load((root / "traceability/authority.yaml").read_text(encoding="utf-8"))
    rules = {r["id"]: r for r in data["rules"]}
    checks = data["checks"]
    errors: list[str] = []
    gates_md = (root / "guidelines/quality-gates.md").read_text(encoding="utf-8")
    build = (root / "template/build.gradle").read_text(encoding="utf-8")

    for r in rules.values():
        file, _, anchor = r["source"].partition("#")
        path = root / file
        if not path.is_file():
            errors.append(f"{r['id']}: 根拠のファイルがありません: {file}")
        elif anchor and anchor not in headings(path):
            errors.append(f"{r['id']}: 根拠の見出しがありません: {r['source']}")

    used: set[str] = set()
    for c in checks:
        for rid in c["rules"]:
            if rid not in rules:
                errors.append(f"{c['id']}: 根拠ルール {rid} が rules にありません（越権）")
            used.add(rid)
        if not re.search(rf"^\|\s*{re.escape(c['id'])}\s*\|", gates_md, re.M):
            errors.append(f"{c['id']}: guidelines/quality-gates.md の表にありません")
        impl = c["implemented_by"]
        if impl in TOOLS:
            if not (root / TOOLS[impl]).exists():
                errors.append(f"{c['id']}: 実体 {TOOLS[impl]} がありません")
        elif impl in PLUGIN_TASKS:
            plugin = PLUGIN_TASKS[impl]
            if plugin and f"id '{plugin}'" not in build:
                errors.append(f"{c['id']}: {impl} を提供するプラグイン {plugin} が template/build.gradle にありません")
        elif f"tasks.register('{impl}'" not in build:
            errors.append(f"{c['id']}: Gradle タスク {impl} が template/build.gradle に登録されていません")

    for rid, r in rules.items():
        if r["enforcement"] == "machine" and rid not in used:
            errors.append(f"{rid}: machine のルールなのにチェックがありません（空文化）")
    return errors


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    errors = verify(root)
    for e in errors:
        print(f"NG {e}")
    print("authority: OK" if not errors else f"authority: {len(errors)} 件の問題")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
