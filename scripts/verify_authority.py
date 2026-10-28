#!/usr/bin/env python3
"""権限のグラフ（traceability/authority.yaml）を検証する（品質ゲート D11）.

- check が参照する rule が存在する（存在しない根拠で検査しない）
- enforcement: machine の rule に、少なくとも 1 つ check がある（ルールが空文化していない）
- rule の source（ガイドラインのファイルと見出し）が実在する
- check の ID が guidelines/quality-gates.md の表にある
- check の実体（Gradle のタスク名・ツール名）が実在する
- template/build.gradle でゲートが弱められていない（チェックは実在しても、効いていなければ空文化と同じ）
  - qualityGate の dependsOn から、authority.yaml の Gradle のゲート（compileJava・spotbugsMain など）が外れていない
  - ignoreFailures・failOnViolation・maxWarnings・ゲートのタスクの enabled は、リテラルの false・true・0・true
    以外にしていない（`= true` のほか `!false`・`true || x`・変数・`Integer.MAX_VALUE` などの式も弱体化とみなす。
    `.set(v)`・`(v)`・`setIgnoreFailures(v)`・`X.enabled = v`・`tasks.withType(Test) { enabled = v }` も見る）
  - ゲートのタスクに onlyIf { … } を付けていない（条件の中身に関わらず）
  - test タスクでテストを除外・絞り込んでいない（exclude・excludeTestsMatching・karate 以外の excludeTags・include 系）
  - D4 の分岐網羅率の下限（branchCoverageFloor）が MIN_BRANCH_COVERAGE 以上で、-P 等で下限より下げると失敗する作りのまま
  - D4 の対象（coverageTargets）から REQUIRED_COVERAGE_TARGETS が外れていない・検証から除外（excludes）していない
- D4 の閾値を外から下げていない（gradle.properties・verify-gates・ワークフローの -PbranchCoverageMinimum /
  ORG_GRADLE_PROJECT_branchCoverageMinimum、この実行の環境変数）
- verify-gates・ワークフローで、ゲートのタスクを -x / --exclude-task で外していない
- verify-gates・ワークフローで、spec-trace（D6〜D8・D10）を弱めていない
  - --min-asserts を 1 未満（0 や変数・式）にしていない（アサーションの無いテストが D7 を通る）
  - verify-gates.sh / .ps1 の spec_trace check から --enforce-drift・--require・--test-results を外していない
- D2・D5 の設定ファイル（checkstyle.xml・spotbugs の exclude.xml）が基準（traceability/gate-config-baseline.yaml）
  より弱くない（モジュールの削除・設定の変更・抑止のフィルタ・除外の追加・設定ファイルの差し替え）

使い方: python scripts/verify_authority.py [ROOT] [--write-baseline]
  --write-baseline  今の checkstyle.xml・exclude.xml を基準として書いてから検証する（強める変更・承認した除外のとき）

終了コード: 0 問題なし / 1 問題あり
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET  # nosec B405  # リポジトリの中の設定ファイル（checkstyle.xml など）だけを読む
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


def _assignments(code: str, prop: str) -> list[tuple[int, str]]:
    """prop の設定（`x = v`・`x v`・`x(v)`・`x.set(v)`・`x.convention(v)`・`setX(v)`）→ [(位置, 値)].

    値は空白と括弧を除いた式の文字列（`!false`・`true||x` などをそのまま返す. 比較 `==` は設定ではない）.
    """
    setter = "set" + prop[:1].upper() + prop[1:]
    pat = re.compile(
        rf"\b(?:{prop}|{setter})(?:\s*=(?!=)|\s*\.\s*(?:set|convention)\s*\(|\s*\(|[ \t]+(?=[!(\w'\"-]))"
        r"([^\n;}]*)"
    )
    out = []
    for m in pat.finditer(code):
        value = re.sub(r"[\s()]", "", m.group(1))
        out.append((m.start(), value))
    return out


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
        for _, value in _assignments(block, "failOnNoMatchingTests"):
            if value != "true":
                errors.append(f"{WEAK}:{line}: test タスクで failOnNoMatchingTests = {value}")
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

    # 値はリテラルだけ許す（`!false`・`true || x`・変数・Integer.MAX_VALUE などの式では弱められる）
    for pos, value in _assignments(code, "ignoreFailures"):
        if value != "false":
            errors.append(
                f"{WEAK}:{_line(code, pos)}: ignoreFailures = {value}（リテラルの false 以外。失敗しても通る）"
            )
    for pos, value in _assignments(code, "failOnViolation"):
        if value != "true":
            errors.append(f"{WEAK}:{_line(code, pos)}: failOnViolation = {value}（リテラルの true 以外。不足でも通る）")
    for pos, value in _assignments(code, "maxWarnings"):
        if value != "0":
            errors.append(f"{WEAK}:{_line(code, pos)}: maxWarnings = {value}（0 にする）")
    for pos, value in _assignments(code, "enabled"):
        if value != "true":
            for t in sorted(_owner_tasks(code, pos) & gradle_tasks):
                errors.append(f"{WEAK}:{_line(code, pos)}: {t} が無効（enabled = {value}。実行されない）")
    for m in re.finditer(r"\bonlyIf\b", code):  # 条件の中身に関わらず、ゲートのタスクを条件付きにしない
        for t in sorted(_owner_tasks(code, m.start()) & gradle_tasks):
            errors.append(f"{WEAK}:{_line(code, m.start())}: {t} が無効（onlyIf {{ … }}。実行されないことがある）")
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
        errors
        + check_coverage_overrides(root, floor or MIN_BRANCH_COVERAGE)
        + check_excluded_tasks(root, gradle_tasks)
        + check_spec_trace_args(root)
        + check_tool_configs(root, code)
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


_MIN_ASSERTS = re.compile(r"--min-asserts(?:\s*=\s*|\s+)(['\"]?)([^\s'\"`]*)\1")
# verify-gates の spec_trace check に必ず付ける引数（D8 の設計書が無いときの失敗・要件の状態・テストの実行結果）
SPEC_TRACE_REQUIRED_ARGS = ("--enforce-drift", "--require", "--test-results")


def _code_lines(text: str) -> str:
    """行コメント（# で始まる行）を空行にする（行番号は保つ）."""
    return "\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.split("\n"))


def _spec_trace_commands(text: str) -> list[tuple[int, str]]:
    """spec_trace check の呼び出し（行末の \\ や ` の継続行をつなげたもの）と、その位置."""
    out = []
    for m in re.finditer(r"(?:spec_trace|spec-trace)\s+check\b", text):
        end = m.end()
        while True:
            nl = text.find("\n", end)
            if nl == -1:
                end = len(text)
                break
            if text[end:nl].rstrip().endswith(("\\", "`")):
                end = nl + 1
                continue
            end = nl
            break
        out.append((m.start(), text[m.start() : end]))
    return out


def check_spec_trace_args(root: Path) -> list[str]:
    """ゲートを実行する経路で、spec-trace（D6〜D8・D10）の引数を弱めていないか."""
    errors: list[str] = []
    for f in _gate_runner_files(root):
        rel = f.relative_to(root).as_posix()
        text = _code_lines(f.read_text(encoding="utf-8-sig"))
        for m in _MIN_ASSERTS.finditer(text):
            value = m.group(2)
            if not value.isdigit() or int(value) < 1:
                errors.append(
                    f"ゲートの弱体化: {rel}:{_line(text, m.start())}: spec-trace の --min-asserts {value or '（空）'}"
                    "（リテラルの 1 以上にする。アサーションの無いテストが D7 を通る）"
                )
        if f.name.startswith("verify-gates."):
            commands = _spec_trace_commands(text)
            if not commands:
                errors.append(f"ゲートの弱体化: {rel} に spec_trace check がありません（D6〜D8・D10 が実行されない）")
            for pos, cmd in commands:
                for arg in SPEC_TRACE_REQUIRED_ARGS:
                    if not re.search(rf"(?<![\w-]){re.escape(arg)}(?![\w-])", cmd):
                        errors.append(
                            f"ゲートの弱体化: {rel}:{_line(text, pos)}: spec_trace check に {arg} がありません"
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


# --- D2・D5 の設定ファイル（checkstyle.xml・exclude.xml）の弱体化 ------------------------------------------

CHECKSTYLE_XML = "template/config/checkstyle/checkstyle.xml"
SPOTBUGS_EXCLUDE_XML = "template/config/spotbugs/exclude.xml"
BASELINE = "traceability/gate-config-baseline.yaml"
# 足すと規約の違反を黙らせられるモジュール（抑止のフィルタ）
SUPPRESSION_MODULES = {
    "SuppressionFilter", "SuppressionXpathFilter", "SuppressionSingleFilter", "SuppressionXpathSingleFilter",
    "SuppressWarningsFilter", "SuppressWarningsHolder", "SuppressionCommentFilter", "SuppressWithNearbyCommentFilter",
    "SuppressWithPlainTextCommentFilter", "SuppressWithNearbyTextFilter", "BeforeExecutionExclusionFileFilter",
}  # fmt: skip
WEAK_SEVERITIES = {"ignore", "info"}
# build.gradle の D5 の作り（空白は無視して比べる）
SPOTBUGS_WIRING = (
    "excludeFilter = file('config/spotbugs/exclude.xml')",
    "effort = com.github.spotbugs.snom.Effort.valueOf('MAX')",
)
SPOTBUGS_FORBIDDEN = ("includeFilter", "onlyAnalyze", "omitVisitors", "baselineFile", "excludeBugsFilter")


def _parse_xml(path: Path) -> ET.Element:
    return ET.fromstring(path.read_bytes())  # nosec B314  # リポジトリの設定ファイルだけ。外部 DTD は読みに行かない


def checkstyle_modules(path: Path) -> list[str]:
    """checkstyle.xml の各モジュール → 'Checker/TreeWalker/LineLength {ignorePattern=…, max=120}' の形の文字列."""
    out: list[str] = []

    def walk(el: ET.Element, prefix: str) -> None:
        name = el.get("name", "?")
        here = f"{prefix}/{name}" if prefix else name
        props = {p.get("name", ""): p.get("value", "") for p in el.findall("property")}
        body = ", ".join(f"{k}={v}" for k, v in sorted(props.items()))
        out.append(f"{here} {{{body}}}")
        for child in el.findall("module"):
            walk(child, here)

    walk(_parse_xml(path), "")
    return out


def _canonical(el: ET.Element) -> str:
    attrs = "".join(f" {k}={v!r}" for k, v in sorted(el.attrib.items()))
    return f"<{el.tag}{attrs}>" + "".join(_canonical(c) for c in el) + f"</{el.tag}>"


def spotbugs_excludes(path: Path) -> list[str]:
    """exclude.xml の除外（Match など直下の要素）を正規化した文字列."""
    return [_canonical(el) for el in _parse_xml(path)]


def current_baseline(root: Path) -> dict[str, list[str]]:
    return {
        "checkstyle_modules": checkstyle_modules(root / CHECKSTYLE_XML),
        "spotbugs_excludes": spotbugs_excludes(root / SPOTBUGS_EXCLUDE_XML),
    }


def check_tool_configs(root: Path, code: str) -> list[str]:
    """D2（checkstyle.xml）・D5（exclude.xml）の設定が、基準（traceability/gate-config-baseline.yaml）より弱くないか.

    - checkstyle.xml: 基準のモジュール（名前・置き場所・プロパティ）が全部ある（消す・値を変えるのは弱体化の恐れ）。
      抑止のフィルタ（SuppressionFilter など）・severity の ignore / info を足していない
    - exclude.xml: 基準に無い除外を足していない（除外を減らすのは自由）
    - build.gradle: 設定ファイルを差し替えていない（configFile・includeFilter など）、D5 の除外・effort の作りのまま
    強める変更（モジュールを足す・除外を減らす）は自由。値を変える・除外を足すときは、レビューで承認してから
    `python scripts/verify_authority.py --write-baseline` で基準を同じ PR で更新する。
    """
    errors: list[str] = []
    base_path = root / BASELINE
    if not base_path.is_file():
        return [f"ゲートの弱体化の基準 {BASELINE} がありません（--write-baseline で作る）"]
    base = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    for rel, kind in ((CHECKSTYLE_XML, "D2"), (SPOTBUGS_EXCLUDE_XML, "D5")):
        if not (root / rel).is_file():
            errors.append(f"ゲートの弱体化: {kind} の設定 {rel} がありません")
    if errors:
        return errors
    try:
        modules = checkstyle_modules(root / CHECKSTYLE_XML)
        excludes = spotbugs_excludes(root / SPOTBUGS_EXCLUDE_XML)
    except ET.ParseError as e:
        return [f"ゲートの弱体化: D2・D5 の設定を XML として読めません: {e}"]

    for m in base.get("checkstyle_modules", []):
        if m not in modules:
            errors.append(
                f"ゲートの弱体化: {CHECKSTYLE_XML} に基準のモジュール「{m}」がありません（消した・設定を変えた。"
                "強める変更なら基準を --write-baseline で更新する）"
            )
    for m in modules:
        name = m.split(" ", 1)[0].rsplit("/", 1)[-1]
        if name in SUPPRESSION_MODULES:
            errors.append(f"ゲートの弱体化: {CHECKSTYLE_XML} に抑止のフィルタ {name}（違反を黙らせられる）")
        for sev in re.findall(r"\bseverity=(\w+)", m):
            if sev in WEAK_SEVERITIES:
                errors.append(
                    f"ゲートの弱体化: {CHECKSTYLE_XML} の {m.split(' ', 1)[0]} が severity={sev}（失敗しない）"
                )
    allowed = set(base.get("spotbugs_excludes", []))
    for x in excludes:
        if x not in allowed:
            errors.append(
                f"ゲートの弱体化: {SPOTBUGS_EXCLUDE_XML} に基準に無い除外 {x}（理由を書いてレビューで承認し、"
                "--write-baseline で基準に足す）"
            )

    for m in re.finditer(r"\b(configFile|configDirectory|config)\s*(?:=(?!=)|\.\s*set\s*\()", code):
        errors.append(
            f"{WEAK}:{_line(code, m.start())}: Checkstyle の {m.group(1)} を差し替えない（{CHECKSTYLE_XML} を使う）"
        )
    for word in SPOTBUGS_FORBIDDEN:
        for m in re.finditer(rf"\b{word}\b", code):
            errors.append(f"{WEAK}:{_line(code, m.start())}: SpotBugs の {word}（D5 の対象・検出を狭める）")
    flat = _squash(code)
    for snippet in SPOTBUGS_WIRING:
        if _squash(snippet) not in flat:
            errors.append(f"{WEAK} の D5 に「{snippet}」がありません")
    if len(re.findall(r"\bexcludeFilter\b", code)) > 1:
        errors.append(f"{WEAK}: SpotBugs の excludeFilter が複数あります（{SPOTBUGS_EXCLUDE_XML} だけを使う）")
    for m in re.finditer(r"\breportLevel\b[^\n]*\bHIGH\b", code):
        errors.append(f"{WEAK}:{_line(code, m.start())}: SpotBugs の reportLevel を HIGH にしない（MEDIUM 以下）")
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


def write_baseline(root: Path) -> Path:
    path = root / BASELINE
    head = (
        "# D2（checkstyle.xml）・D5（exclude.xml）の基準。\n"
        "# scripts/verify_authority.py（D11）がこれより弱い設定を検出する。更新は\n"
        "# python scripts/verify_authority.py --write-baseline（強める変更、またはレビューで承認した除外のときだけ）\n"
    )
    path.write_text(
        head + yaml.safe_dump(current_baseline(root), allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
        newline="\n",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    write = "--write-baseline" in args
    args = [a for a in args if a != "--write-baseline"]
    root = Path(args[0]) if args else ROOT
    if write:
        print(f"基準を書きました: {write_baseline(root).relative_to(root).as_posix()}")
    errors = verify(root)
    for e in errors:
        print(f"NG {e}")
    print("authority: OK" if not errors else f"authority: {len(errors)} 件の問題")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
