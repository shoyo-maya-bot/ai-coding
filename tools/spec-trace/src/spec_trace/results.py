"""JUnit 形式のテスト結果 XML（Gradle の build/test-results、pytest --junitxml など）を読む.

proven の裏付けに「テストが実行されて成功した」ことを加えるために使う（check --test-results）。
読むのは自分のビルドが出した結果ファイルだけで、外から受け取った XML を読む用途は想定しない。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # nosec B405  # 自分のビルドが出したテスト結果だけを読む
from dataclasses import dataclass, field
from pathlib import Path

from devtools_common.cli import UsageError

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"


@dataclass
class Case:
    classname: str  # 例: com.example.app.order.OrderImportServiceTest / tests.test_x.TestClass
    name: str  # 例: parseRejects(String, String)[1] / test_required[param]
    outcome: str
    message: str = ""
    source: str = ""  # 読んだ XML ファイル


@dataclass
class TestResults:
    cases: list[Case] = field(default_factory=list)
    files: int = 0

    def find(self, owner: str | None, method: str) -> list[Case]:
        """クラス名（単純名）とメソッド名に当たる結果（パラメータ化テストは全実行分）."""
        out = []
        for c in self.cases:
            if _method_name(c.name) != method:
                continue
            if owner is None or _simple_class(c.classname) == owner:
                out.append(c)
        return out


    def names_in_class(self, owner: str | None, limit: int = 5) -> list[str]:
        """クラス（単純名）の結果にあるテスト名（見つからないときの手がかり）."""
        if owner is None:
            return []
        names = [c.name for c in self.cases if _simple_class(c.classname) == owner]
        return names[:limit]


def _method_name(name: str) -> str:
    """'importsValid()' / 'parseRejects(String, String)[1]' / 'test_x[a-b]' → メソッド名."""
    return re.split(r"[(\[]", name, maxsplit=1)[0].strip()


def _simple_class(classname: str) -> str:
    """'com.example.FooTest' / 'Outer$Inner' / 'tests.test_x.TestClass' → 最後の名前."""
    return re.split(r"[.$]", classname)[-1]


def _outcome(tc: ET.Element) -> tuple[str, str]:
    for tag, outcome in (("failure", FAILED), ("error", FAILED), ("skipped", SKIPPED)):
        el = tc.find(tag)
        if el is not None:
            return outcome, (el.get("message") or el.get("type") or (el.text or "").strip())[:200]
    return PASSED, ""


def load_results(paths: list[Path]) -> TestResults:
    """ファイルまたはディレクトリ（中の *.xml を再帰で）を読む. 1 つも読めなければ誤りにする（黙って通さない）."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*.xml") if f.is_file())
        elif p.is_file():
            files.append(p)
        else:
            raise UsageError(f"テスト結果が見つかりません: {p}（先にテストを実行する）")
    if not files:
        raise UsageError(f"テスト結果の XML がありません: {', '.join(map(str, paths))}（先にテストを実行する）")
    results = TestResults()
    for f in files:
        try:
            root = ET.parse(f).getroot()  # nosec B314  # 自分のビルドが出したテスト結果だけを読む
        except ET.ParseError as e:
            raise UsageError(f"テスト結果の XML を読めません: {f}（{e}）") from e
        if root.tag not in ("testsuite", "testsuites"):
            raise UsageError(f"JUnit 形式のテスト結果ではありません: {f}（ルート要素 {root.tag}）")
        results.files += 1
        for tc in root.iter("testcase"):
            outcome, message = _outcome(tc)
            results.cases.append(Case(tc.get("classname", ""), tc.get("name", ""), outcome, message, f.name))
    return results
