#!/usr/bin/env python3
"""権限のグラフ（traceability/authority.yaml）を検証する（品質ゲート D11）.

- check が参照する rule が存在する（存在しない根拠で検査しない）
- enforcement: machine の rule に、少なくとも 1 つ check がある（ルールが空文化していない）
- rule の source（ガイドラインのファイルと見出し）が実在する
- check の ID が guidelines/quality-gates.md の表にある
- check の実体（Gradle のタスク名・ツール名）が実在する
- template/build.gradle でゲートが弱められていない（チェックは実在しても、効いていなければ空文化と同じ）
  - qualityGate の dependsOn から、authority.yaml の Gradle のゲート（compileJava・spotbugsMain など）が外れていない
  - ignoreFailures = true・failOnViolation = false・maxWarnings が 0 以外・ゲートのタスクの enabled = false が無い
    （`= true` のほか `.set(true)`・`(true)`・`setIgnoreFailures(true)`・`X.enabled = false`・`onlyIf { false }`・
    `tasks.withType(Test) { enabled = false }` も見る）
  - test タスクでテストを除外・絞り込んでいない（exclude・excludeTestsMatching・karate 以外の excludeTags・include 系）
  - D4 の分岐網羅率の下限（branchCoverageFloor）が MIN_BRANCH_COVERAGE 以上で、-P 等で下限より下げると失敗する作りのまま
  - D4 の対象（coverageTargets）から REQUIRED_COVERAGE_TARGETS が外れていない・検証から除外（excludes）していない
- D4 の閾値を外から下げていない（gradle.properties・verify-gates・ワークフローの -PbranchCoverageMinimum /
  ORG_GRADLE_PROJECT_branchCoverageMinimum、この実行の環境変数）
- verify-gates・ワークフローで、ゲートのタスクを -x / --exclude-task で外していない

終了コード: 0 問題なし / 1 問題あり
"""

from __future__ import annotations

import os
import re
import sys
from decimal import Decimal, InvalidOperation
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


# D4 の分岐網羅率の下限. 目標は 100%（guidelines/quality-gates.md）。上げるときは build.gradle と同じ PR で上げる。
# 下げる変更はゲートのこじ開け（guidelines/workflow.md の禁止事項）なので、レビューで止める
MIN_BRANCH_COVERAGE = Decimal("0.80")
COVERAGE_PROP = "branchCoverageMinimum"
# build.gradle の D4 の作り（下限の定義・既定値・下回ったら失敗・検証に使う）. 空白は無視して比べる
COVERAGE_WIRING = (
    "def branchMinimum = (project.findProperty('branchCoverageMinimum') ?: branchCoverageFloor.toPlainString())"
    " as BigDecimal",
    "if (branchMinimum < branchCoverageFloor) {",
    "minimum = branchMinimum",
    "includes: coverageTargets",
)
# D4 の対象（業務ロジック）. 足すのは自由だが、外す（対象を狭めて網羅率を上げる）のはゲートのこじ開け
REQUIRED_COVERAGE_TARGETS = ("com/example/app/**/*Service.class", "com/example/app/**/batch/*Job.class")
WEAK = "ゲートの弱体化: template/build.gradle"  # 指摘の先頭
# test タスクで除外してよいタグ（Karate は karateTest タスクで別に実行する）
ALLOWED_EXCLUDE_TAGS = {"karate"}
# tasks.withType(…) の型 → その型のゲートのタスク
TASK_TYPES = {
    "Test": {"test"},
    "JavaCompile": {"compileJava"},
    "Checkstyle": {"checkstyleMain", "checkstyleTest"},
    "SpotBugsTask": {"spotbugsMain"},
    "JacocoCoverageVerification": {"jacocoTestCoverageVerification"},
}
_SET = r"\s*(?:=|\.(?:set|convention)\s*\(|\(|)\s*"  # `x = v`・`x v`・`x(v)`・`x.set(v)`・`x.convention(v)`


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _quality_gate_deps(build: str) -> set[str] | None:
    """tasks.register('qualityGate') { … } の dependsOn に書かれたタスク名（ブロックが無ければ None）."""
    m = re.search(r"tasks\.register\(\s*'qualityGate'\s*\)\s*\{", build)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(build) and depth:
        depth += {"{": 1, "}": -1}.get(build[i], 0)
        i += 1
    block = build[m.end() : i]
    deps: set[str] = set()
    for d in re.finditer(r"dependsOn\s*\(?\s*((?:['\"][\w:]+['\"]\s*,\s*)*['\"][\w:]+['\"])", block):
        deps |= set(re.findall(r"['\"]([\w:]+)['\"]", d.group(1)))
    return deps


def _blocks(code: str, header: str) -> list[tuple[int, str]]:
    """header（正規表現. 末尾の { を含む）で始まるブロック → [(位置, 中身)]."""
    out = []
    for m in re.finditer(header, code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        out.append((m.start(), code[m.end() : i - 1]))
    return out


def _line(code: str, pos: int) -> int:
    return code.count("\n", 0, pos) + 1


def _owner_tasks(code: str, pos: int) -> set[str]:
    """pos の設定（enabled = false など）がどのタスクのものか. `X.enabled` の X か、囲むブロックの見出しから決める."""
    before = code[:pos]
    m = re.search(
        r"(?:tasks\s*\.\s*(?:named|getByName)\(\s*['\"](\w+)['\"]\s*\)|(?:tasks\s*\.\s*)?(\w+))\s*\.\s*$", before
    )
    if m:
        return {m.group(1) or m.group(2)}
    depth, i = 0, pos - 1
    while i >= 0:  # 囲む { を探す
        depth += {"}": 1, "{": -1}.get(code[i], 0)
        if depth < 0:
            break
        i -= 1
    if i < 0:
        return set()
    head = code[max(code.rfind("\n", 0, i), code.rfind(";", 0, i), code.rfind("}", 0, i)) + 1 : i].strip()
    if m := re.search(r"tasks\s*\.\s*(?:named|getByName)\(\s*['\"](\w+)['\"]", head):
        return {m.group(1)}
    if m := re.search(r"withType\(\s*(?:[\w.]+\.)?(\w+)\s*\)", head):
        return TASK_TYPES.get(m.group(1), set())
    if m := re.fullmatch(r"(?:tasks\s*\.\s*)?(\w+)", head):
        return {m.group(1)}
    return set()


def _test_task_blocks(code: str) -> list[tuple[int, str]]:
    """test タスクの設定ブロック（tasks.named('test') { }・test { }・tasks.withType(Test) { }）."""
    return (
        _blocks(code, r"tasks\s*\.\s*(?:named|getByName)\(\s*['\"]test['\"]\s*\)\s*\{")
        + _blocks(code, r"(?m)^\s*(?:tasks\s*\.\s*)?test\s*\{")
        + _blocks(code, r"tasks\s*\.\s*withType\(\s*Test\s*\)\s*(?:\.configureEach\s*)?\{")
    )


def check_test_filters(code: str) -> list[str]:
    """test タスクでテストを除外・絞り込んでいないか（除外したテストは D3・D4 に効かない）."""
    errors: list[str] = []
    for start, block in _test_task_blocks(code):
        line = _line(code, start)
        for m in re.finditer(
            r"\b(exclude|excludes|setExcludes|excludeTestsMatching|include|includes|setIncludes|includeTestsMatching|includeTags)\b",
            block,
        ):
            errors.append(f"{WEAK}:{line}: test タスクで {m.group(1)}（テストを除外・絞り込むと D3・D4 に効かない）")
        for m in re.finditer(r"\bexcludeTags\b([^\n]*)", block):
            tags = set(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))
            extra = sorted(tags - ALLOWED_EXCLUDE_TAGS)
            if extra or not tags:
                errors.append(
                    f"{WEAK}:{line}: test タスクで excludeTags {', '.join(extra) or m.group(1).strip()}"
                    f"（除外してよいのは {', '.join(sorted(ALLOWED_EXCLUDE_TAGS))} だけ）"
                )
        if re.search(r"\bfailOnNoMatchingTests" + _SET + "false", block):
            errors.append(f"{WEAK}:{line}: test タスクで failOnNoMatchingTests = false")
    return errors


def check_coverage_targets(code: str) -> list[str]:
    """D4 の対象（coverageTargets）を狭めていないか・検証から除外していないか."""
    errors: list[str] = []
    m = re.search(r"def\s+coverageTargets\s*=\s*\[([^\]]*)\]", code)
    targets = set(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))) if m else set()
    for t in REQUIRED_COVERAGE_TARGETS:
        if t not in targets:
            errors.append(f"{WEAK} の D4 の対象 coverageTargets に {t} がありません（対象を狭めない）")
    for start, block in _blocks(code, r"jacocoTestCoverageVerification\s*\{"):
        for x in re.finditer(r"\b(excludes?|setExcludes)\b", block):
            errors.append(
                f"{WEAK}:{_line(code, start)}: jacocoTestCoverageVerification で {x.group(1)}（D4 の対象から外さない）"
            )
    return errors


def check_gate_strength(root: Path, gradle_tasks: set[str]) -> list[str]:
    """template/build.gradle でゲートが弱められていないか（D11. チェックが実在しても効いていなければ空文化と同じ）."""
    errors: list[str] = []
    build = (root / "template/build.gradle").read_text(encoding="utf-8")
    code = "\n".join(re.sub(r"//.*$", "", ln) for ln in build.splitlines())  # 行コメントは見ない

    deps = _quality_gate_deps(code)
    if deps is None:
        errors.append("ゲートの弱体化: template/build.gradle に qualityGate タスクがありません")
    else:
        for t in sorted(gradle_tasks - deps):
            errors.append(f"ゲートの弱体化: qualityGate の dependsOn に {t} がありません（そのゲートが実行されない）")

    for m in re.finditer(r"\b(?:ignoreFailures|setIgnoreFailures)" + _SET + r"(true)\b", code):
        errors.append(f"{WEAK}:{_line(code, m.start())}: ignoreFailures = true（失敗しても通る）")
    for m in re.finditer(r"\b(?:failOnViolation|setFailOnViolation)" + _SET + r"(false)\b", code):
        errors.append(f"{WEAK}:{_line(code, m.start())}: failOnViolation = false（不足でも通る）")
    for m in re.finditer(r"\b(?:maxWarnings|setMaxWarnings)" + _SET + r"(\d+)", code):
        if int(m.group(1)) != 0:
            errors.append(f"{WEAK}:{_line(code, m.start())}: maxWarnings = {m.group(1)}（0 にする）")
    for m in re.finditer(r"\b(?:enabled|setEnabled)" + _SET + r"false\b|\bonlyIf\s*\{\s*false\s*\}", code):
        for t in sorted(_owner_tasks(code, m.start()) & gradle_tasks):
            errors.append(
                f"{WEAK}:{_line(code, m.start())}: {t} が無効（enabled = false・onlyIf {{ false }}。実行されない）"
            )
    errors += check_test_filters(code)
    errors += check_coverage_targets(code)

    floor_m = re.search(r"def\s+branchCoverageFloor\s*=\s*new\s+BigDecimal\(\s*'([^']*)'\s*\)", code)
    floor = _decimal(floor_m.group(1)) if floor_m else None
    if floor is None:
        errors.append(
            "ゲートの弱体化: template/build.gradle に D4 の下限 branchCoverageFloor = new BigDecimal('…') がありません"
        )
    elif floor < MIN_BRANCH_COVERAGE:
        errors.append(
            f"ゲートの弱体化: D4 の分岐網羅率の下限 branchCoverageFloor = {floor} が {MIN_BRANCH_COVERAGE} より低い"
            "（閾値を下げない。目標は 100%）"
        )
    flat = _squash(code)
    for snippet in COVERAGE_WIRING:
        if _squash(snippet) not in flat:
            errors.append(f"{WEAK} の D4 に「{snippet}」がありません（下げられる）")
    return (
        errors + check_coverage_overrides(root, floor or MIN_BRANCH_COVERAGE) + check_excluded_tasks(root, gradle_tasks)
    )


_EXCLUDE_TASK = re.compile(r"(?:^|\s)(?:-x|--exclude-task)[\s=]+['\"]?:?(\w+)", re.M)


def _gate_runner_files(root: Path) -> list[Path]:
    files = [root / "scripts/verify-gates.sh", root / "scripts/verify-gates.ps1"]
    wf = root / ".github/workflows"
    if wf.is_dir():
        files += sorted(p for p in wf.iterdir() if p.suffix in (".yml", ".yaml"))
    return [f for f in files if f.is_file()]


def check_excluded_tasks(root: Path, gradle_tasks: set[str]) -> list[str]:
    """ゲートを実行する経路（verify-gates・ワークフロー）で、ゲートのタスクを -x で外していないか."""
    errors: list[str] = []
    for f in _gate_runner_files(root):
        text = f.read_text(encoding="utf-8")
        for m in _EXCLUDE_TASK.finditer(text):
            if m.group(1) in gradle_tasks | {"qualityGate", "check"}:
                errors.append(
                    f"ゲートの弱体化: {f.relative_to(root).as_posix()}:{_line(text, m.start())}: -x {m.group(1)}"
                    "（そのゲートが実行されない）"
                )
    return errors


_OVERRIDE = re.compile(
    rf"(?:-P|-Dorg\.gradle\.project\.|ORG_GRADLE_PROJECT_|^\s*){COVERAGE_PROP}\s*[=:]\s*['\"]?([^\s'\"]+)", re.M
)


def check_coverage_overrides(root: Path, floor: Decimal) -> list[str]:
    """D4 の閾値を下限より下げる指定が、ゲートを実行する経路（設定・スクリプト・CI・この実行の環境）に無いか."""
    errors: list[str] = []
    files = [root / "template/gradle.properties", *_gate_runner_files(root)]
    for f in files:
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        for m in _OVERRIDE.finditer(text):
            value = _decimal(m.group(1))
            if value is None or value < floor:
                line = text.count("\n", 0, m.start()) + 1
                errors.append(
                    f"ゲートの弱体化: {f.relative_to(root).as_posix()}:{line}: {COVERAGE_PROP} を {m.group(1)} に"
                    f"（下限 {floor} より低い）"
                )
    for name in (f"ORG_GRADLE_PROJECT_{COVERAGE_PROP}",):
        raw = os.environ.get(name)
        if raw is not None and ((v := _decimal(raw)) is None or v < floor):
            errors.append(f"ゲートの弱体化: 環境変数 {name}={raw}（下限 {floor} より低い）")
    for name in ("GRADLE_OPTS", "JAVA_OPTS", "JAVA_TOOL_OPTIONS"):
        for m in _OVERRIDE.finditer(os.environ.get(name, "")):
            v = _decimal(m.group(1))
            if v is None or v < floor:
                errors.append(f"ゲートの弱体化: 環境変数 {name} で {COVERAGE_PROP}={m.group(1)}（下限 {floor} 未満）")
    return errors


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
    gradle_tasks: set[str] = set()
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
            gradle_tasks.add(impl)
            plugin = PLUGIN_TASKS[impl]
            if plugin and f"id '{plugin}'" not in build:
                errors.append(f"{c['id']}: {impl} を提供するプラグイン {plugin} が template/build.gradle にありません")
        elif f"tasks.register('{impl}'" not in build:
            errors.append(f"{c['id']}: Gradle タスク {impl} が template/build.gradle に登録されていません")
        else:
            gradle_tasks.add(impl)

    for rid, r in rules.items():
        if r["enforcement"] == "machine" and rid not in used:
            errors.append(f"{rid}: machine のルールなのにチェックがありません（空文化）")
    return errors + check_gate_strength(root, gradle_tasks)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    errors = verify(root)
    for e in errors:
        print(f"NG {e}")
    print("authority: OK" if not errors else f"authority: {len(errors)} 件の問題")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
