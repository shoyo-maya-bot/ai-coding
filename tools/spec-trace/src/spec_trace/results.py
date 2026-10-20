"""JUnit 形式のテスト結果 XML（Gradle の build/test-results、pytest --junitxml など）を読む.

proven の裏付けに「テストが実行されて成功した」ことを加えるために使う（check --test-results）。
読むのは自分のビルドが出した結果ファイルだけで、外から受け取った XML を読む用途は想定しない。
"""

from __future__ import annotations

import functools
import os
import re
import xml.etree.ElementTree as ET  # nosec B405  # 自分のビルドが出したテスト結果だけを読む
from dataclasses import dataclass, field
from pathlib import Path

from devtools_common.cli import UsageError

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"
_INVOCATION = re.compile(r"^\[\d+\]")  # パラメータ化テストの 1 回分（Gradle の JUnit XML の名前）


@dataclass
class Case:
    classname: str  # 例: com.example.app.order.OrderImportServiceTest / tests.test_x.TestClass
    name: str  # 例: parseRejects(String, String)[1] / test_required[param]
    outcome: str
    message: str = ""
    source: str = ""  # 読んだ XML ファイル


_PACKAGE = re.compile(r"^\s*package\s+([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*;?", re.M)
_JVM_SUFFIXES = {".java", ".kt", ".kts", ".groovy", ".scala"}


@dataclass(frozen=True)
class Origin:
    """テストのソースの場所. 結果の classname を、単純なクラス名ではなくパッケージ・モジュールまで含めて照合する.

    - Java / Kotlin 等: ソースの package 宣言 + クラス名（com.example.a.FooTest）。入れ子のクラスは Outer$Inner
    - Python: ファイルのパス（拡張子なし）。pytest の classname（rootdir からの相対の「.」区切り）と、
      短い方がもう一方の末尾に一致すること（rootdir の違いで先頭が増減しても照合できる）。
      ただし一致が末尾の 1 つ（ファイル名）だけで、ソースがフォルダの中にあるときは、同じ名前のテストファイルが
      プロジェクトにほかに無い場合だけ一致とみなす
      （tests/unit/test_x.py の裏付けに tests/e2e/test_x.py の結果を使わない）
    - それ以外（TypeScript など）: None（従来どおり単純名で照合）
    """

    kind: str  # "jvm" / "python"
    package: str = ""  # jvm: パッケージ（無名パッケージは ""）
    module: tuple[str, ...] = ()  # python: ファイルのパスの各部（拡張子なし）
    unique_name: bool = True  # python: 同じファイル名のテストファイルがプロジェクトにほかに無いか

    @classmethod
    def of(cls, path: Path, rel: str) -> Origin | None:
        if path.suffix in _JVM_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            m = _PACKAGE.search(text)
            return cls("jvm", package=re.sub(r"\s+", "", m.group(1)) if m else "")
        if path.suffix == ".py":
            parts = tuple(p for p in Path(rel).with_suffix("").parts if p not in (".", "..", "/", "\\"))
            unique = True
            if len(parts) > 1 and ".." not in Path(rel).parts:
                root = path.resolve()
                for _ in Path(rel).parts:
                    root = root.parent
                unique = _same_name_files(str(root), path.name) <= 1
            return cls("python", module=parts, unique_name=unique)
        return None

    def matches(self, classname: str) -> bool:
        if self.kind == "jvm":
            if not self.package:
                return "." not in classname
            prefix = self.package + "."
            return classname.startswith(prefix) and "." not in classname[len(prefix) :]
        parts = tuple(classname.split("."))
        module = parts[:-1] if _in_class(classname) else parts
        n = min(len(module), len(self.module))
        if n == 0 or module[-n:] != self.module[-n:]:
            return False
        # ファイル名だけの一致（classname が test_x で、ソースが tests/unit/test_x.py）は、
        # 同名のファイルがほかに無いときだけ
        return n > 1 or len(self.module) == 1 or self.unique_name


_SKIP_DIRS = {"node_modules", "site-packages", "build", "dist", "venv", "__pycache__"}


@functools.lru_cache(maxsize=256)
def _same_name_files(root: str, name: str) -> int:
    """root の下にある name というファイルの数（隠しフォルダ・仮想環境・ビルドの出力は見ない）."""
    count = 0
    for _dir, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
        count += files.count(name)
    return count


@dataclass
class TestResults:
    cases: list[Case] = field(default_factory=list)
    files: int = 0

    def find(
        self,
        owner: str | None,
        method: str,
        params: tuple[str, ...] | None = None,
        case: str | None = None,
        origin: Origin | None = None,
        display: str | None = None,
    ) -> list[Case]:
        """クラス名とメソッド名に当たる結果（パラメータ化テストは全実行分）.

        - origin（テストのソースの場所）があれば、classname をパッケージ・モジュールまで含めて照合する
          （別のパッケージにある同名のテストクラスの結果を、このテストの結果とみなさない）

        - 結果の名前の「(引数の型)」と「[id]」を外してメソッド名を比べる
          （test_x[case1]・parseRejects(String)[1] → test_x・parseRejects の実行分）
        - case（対応表に test_x[case1] のように 1 件だけ書いたとき）は、その id の実行分だけを見る
        - owner が無い（モジュールの関数 test_x）ときは、クラスの中の同名のメソッド（pytest の classname が
          モジュール.クラス になるもの）を混ぜない。クラスの外の同名の関数が結果に無いときだけ、全部を見る
        - params（パラメータ化テストの引数名. パラメータ化テストでなければ None）があり、結果の名前にメソッド名が無い
          （Gradle は「[1] line = "…", message = "…"」にする）ときは、同じクラスの「[番号] 引数名 = 値, …」のうち、
          **引数名の並びがこのメソッドと同じ** 結果だけをこのメソッドの実行分とみなす
          （別のパラメータ化テストの成功を数えない。引数名の並びが同じメソッドが 2 つ以上あると区別できないので、
          どちらの実行分ともみなさない＝実行されていない扱い）
        - display（JUnit 5 の @DisplayName の表示名. 同じクラスで一意なものだけ）があり、結果の名前にメソッド名が無い
          （Gradle は @DisplayName の付いたテストの結果の名前を表示名にする）ときは、同じクラスの、名前が表示名と
          一致する結果をこのメソッドの実行分とみなす
        """
        cases = [c for c in self.cases if origin is None or origin.matches(c.classname)]
        out = [c for c in cases if _method_name(c.name) == method]
        if owner is not None:
            out = [c for c in out if _simple_class(c.classname) == owner]
        else:
            module_level = [c for c in out if not _in_class(c.classname)]
            out = module_level or out
        if not out and params and owner is not None:
            out = [
                c
                for c in cases
                if _simple_class(c.classname) == owner
                and _INVOCATION.match(c.name)
                and invocation_params(c.name) == params
            ]
        if not out and display and owner is not None and case is None:
            out = [c for c in cases if _simple_class(c.classname) == owner and c.name == display]
        if case is not None:
            out = [c for c in out if _case_id(c.name) == case]
        return out

    def find_scenario(self, scenario: str, feature: str = "") -> list[Case]:
        """シナリオ名に当たる結果（Karate の JUnit XML. 名前の先頭の「[1:5] 」などの番号は外して比べる）.

        同じ名前のシナリオが別の Feature にもあるときは、classname の最後が Feature のファイル名（拡張子なし）の
        結果を優先する。
        """
        out = [c for c in self.cases if _scenario_name(c.name) == scenario]
        same_feature = [c for c in out if feature and _simple_class(c.classname) == feature]
        return same_feature or out

    def names_in_class(self, owner: str | None, limit: int = 5) -> list[str]:
        """クラス（単純名）の結果にあるテスト名（見つからないときの手がかり. classname 付き）."""
        if owner is None:
            return []
        names = [f"{c.classname}#{c.name}" for c in self.cases if _simple_class(c.classname) == owner]
        return names[:limit]


_SCENARIO_PREFIX = re.compile(r"^\[[\d.:]+\]\s*|^(?:Scenario(?: Outline)?|Example|シナリオ(?:アウトライン)?)\s*:\s*")


def _scenario_name(name: str) -> str:
    """'[1:5] 登録した会員を照会できる' / 'Scenario: x' → シナリオ名."""
    prev = None
    while prev != name:
        prev, name = name, _SCENARIO_PREFIX.sub("", name, count=1)
    return name.strip()


_PARAM = re.compile(r"([A-Za-z_$][\w$]*) = ")


def invocation_params(name: str) -> tuple[str, ...] | None:
    """'[1] line = "a, b", message = "c"' → ('line', 'message'). 引数名の無い名前（'[1] a, b'）は None.

    文字列の値（"…"）の中の「, x = 」は引数名とみなさない。
    """
    m = _INVOCATION.match(name)
    if not m:
        return None
    rest = name[m.end() :].lstrip()
    names: list[str] = []
    while rest:
        pm = _PARAM.match(rest)
        if not pm:
            return None
        names.append(pm.group(1))
        rest = rest[pm.end() :]
        if rest.startswith('"'):  # 文字列の値: 閉じる " まで（\" は値の一部）
            i = 1
            while i < len(rest) and rest[i] != '"':
                i += 2 if rest[i] == "\\" else 1
            rest = rest[i + 1 :]
            if rest and not rest.startswith(", "):
                return None
        else:  # 文字列以外の値: 次の「, 引数名 = 」まで
            nxt = re.search(r", (?=[A-Za-z_$][\w$]* = )", rest)
            rest = rest[nxt.start() :] if nxt else ""
        rest = rest[2:] if rest.startswith(", ") else rest
    return tuple(names) or None


def _method_name(name: str) -> str:
    """'importsValid()' / 'parseRejects(String, String)[1]' / 'test_x[a-b]' → メソッド名."""
    return re.split(r"[(\[]", name, maxsplit=1)[0].strip()


def _case_id(name: str) -> str | None:
    """'test_x[case1]' → 'case1'、'parseRejects(String)[1]' → '1'、'[2] s = "c"'（Gradle 9）→ '2'、'test_x' → None."""
    m = re.match(r"^\[(\d+)\]", name)
    if m:
        return m.group(1)
    head = re.split(r"[(\[]", name, maxsplit=1)[0]
    rest = name[len(head) :]
    if rest.startswith("("):
        depth = 0
        for i, ch in enumerate(rest):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0:
                rest = rest[i + 1 :]
                break
    if rest.startswith("[") and rest.endswith("]"):
        return rest[1:-1]
    return None


def _in_class(classname: str) -> bool:
    """pytest の classname がクラスを指すか（tests.test_x.TestFoo → True、tests.test_x → False）. Java は常に True."""
    last = re.split(r"[.$]", classname)[-1]
    return bool(last) and (last[0].isupper() or "$" in classname)


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
