"""ソースコード・テストコードの中身を確かめる（存在するか・アサーションがあるか）.

Python は構文木（ast）で正確に調べる。それ以外の言語（Java / Kotlin / C# / TypeScript / JavaScript / Go など）は
正規表現と波かっこの対応で調べる近似。どちらも「存在すること」「最低限の検証があること」までを保証し、
テストの意味的な妥当性は人のレビュー（と必要ならミューテーションテスト）で担保する。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# Python 以外でアサーションとみなす呼び出し. 「to で始まる・should で始まるメソッド」のような広い形にすると、
# toString() / toList() / toUpperCase() などの普通の呼び出しまで数えてしまうので、ライブラリごとの名前を明示する.
_ASSERT_NAMES = [
    # JUnit 4/5・TestNG・Hamcrest・AssertJ・kotlin.test:
    #   assertEquals / assertThat / assertThatThrownBy / assertThrows …
    r"\bassert[A-Z_]\w*\s*\(",
    r"\bassert\s*\(",  # Node の assert(x)・C の assert
    r"\bfail\s*\(",
    # xUnit・NUnit・MSTest（C#）、testify（Go）: Assert.Equal( / assert.Equal( / require.NoError(
    r"\b(?:Assert|CollectionAssert|StringAssert|assert|require)\.\w+\s*\(",
    # Mockito: verify(mock).x() / verifyNoInteractions / verifyNoMoreInteractions / verifyZeroInteractions
    # BDDMockito: then(m).should()
    r"\bverify(?:NoInteractions|NoMoreInteractions|ZeroInteractions)?\s*\(",
    r"\.should(?:HaveNoInteractions|HaveNoMoreInteractions|HaveZeroInteractions)?\s*\(",
    # Spring: MockMvc の andExpect / andExpectAll
    #   WebTestClient の expectStatus / expectBody / expectHeader / expectCookie
    r"\.andExpect(?:All)?\s*\(",
    r"\.expect(?:Status|Body|BodyList|Header|Cookie)\s*\(",
    # Jest・Vitest・Chai（expect 1 回で 1 件。後ろの .toBe() などは数えない）
    r"\bexpect\s*\(",
    # Kotest・Chai（should）: x.shouldBe(1) / shouldThrow<…> { } / x.should(…)
    r"\bshould[A-Z]\w*\s*[(<{]",
    # Go の testing
    r"\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\s*\(",
]
_ASSERT_CALL = re.compile("|".join(_ASSERT_NAMES))
_CLASS_DECL = r"(?:class|interface|enum|record|object|struct|trait)"


@dataclass
class Lookup:
    found: bool
    asserts: int = 0  # 見つかった関数本体のアサーション数（数えられない場合は -1）
    detail: str = ""


def split_case(symbol: str) -> tuple[str, str | None]:
    """パラメータ化テストの 1 件を指す書き方を分ける.

    'test_x[case1]' → ('test_x', 'case1')、'Class#method[1.5-a]' → ('Class#method', '1.5-a')、
    'test_x' → ('test_x', None).
    角かっこの中（pytest の id）には . や :: が入ることがあるので、クラス名とメソッド名に分ける前に外す。
    """
    i = symbol.find("[")
    if i > 0 and symbol.endswith("]"):
        return symbol[:i], symbol[i + 1 : -1]
    return symbol, None


def split_symbol(symbol: str) -> tuple[str | None, str]:
    """'Class#method' / 'Class.method' / 'method' → (クラス名 or None, 名前). 末尾の [id] は外す."""
    symbol, _ = split_case(symbol)
    for sep in ("#", "::", "."):
        if sep in symbol:
            owner, _, name = symbol.rpartition(sep)
            return owner.split(sep)[-1] or None, name
    return None, symbol


# --- Python ---------------------------------------------------------------


def _py_asserts(node: ast.AST) -> int:
    n = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            n += 1
        elif isinstance(sub, ast.Call):
            f = sub.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if name.startswith(("assert", "assert_")) or name in {"raises", "fail", "expect"}:
                n += 1
    return n


def _py_lookup(text: str, symbol: str) -> Lookup:
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return Lookup(False, detail=f"構文エラーのため解析できません（{e.lineno} 行目）")
    owner, name = split_symbol(symbol)
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if owner is not None:
            if isinstance(node, ast.ClassDef) and node.name == owner:
                for child in node.body:
                    if isinstance(child, defs) and child.name == name:
                        return Lookup(True, _py_asserts(child))
        elif isinstance(node, defs) and node.name == name:
            return Lookup(True, _py_asserts(node))
    return Lookup(False)


# --- その他の言語（近似） -----------------------------------------------------


def _strip_comments_and_strings(text: str) -> str:
    """// コメント・/* */・文字列リテラルを空白に置き換える（位置は保つ）.

    Java 15 以降のテキストブロック・Kotlin の raw 文字列（\"\"\" … \"\"\"）も 1 つの文字列として外す
    （中の assertThat( や } をコードとして数えない）。
    """

    def blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return re.sub(
        r'//[^\n]*|/\*.*?\*/|"""(?:\\.|[^\\])*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`[^`]*`',
        blank,
        text,
        flags=re.S,
    )


def _body_after(code: str, start: int) -> str | None:
    """start 以降で最初の { から対応する } までを返す（宣言の途中に ; があれば本体なし）."""
    i = start
    while i < len(code) and code[i] not in "{;":
        i += 1
    if i >= len(code) or code[i] == ";":
        return None
    depth = 0
    for j in range(i, len(code)):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                return code[i + 1 : j]
    return code[i + 1 :]


def _generic_lookup(text: str, symbol: str) -> Lookup:
    code = _strip_comments_and_strings(text)
    owner, name = split_symbol(symbol)
    region = code
    if owner:
        m = re.search(rf"\b{_CLASS_DECL}\s+{re.escape(owner)}\b", code)
        if not m:
            return Lookup(False, detail=f"クラス {owner} が見つかりません")
        region = _body_after(code, m.end()) or ""
        if name == owner:
            return Lookup(True, -1)
    # 宣言らしい行: 行頭から（修飾子・型・アノテーション）+ 名前 + "("。呼び出し（式の途中・行末 ;）は除く
    decl = re.compile(
        rf"(?m)^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*(?:[\w<>\[\],.?:*&]+[ \t]+)*{re.escape(name)}[ \t]*(?:<[^>]*>)?[ \t]*\("
    )
    for m in decl.finditer(region):
        line_end = region.find("\n", m.end())
        line = region[m.start() : line_end if line_end >= 0 else len(region)]
        if line.rstrip().endswith(";") or re.match(r"\s*(?:return|new|throw)\b", line):
            continue
        body = _body_after(region, m.end())
        if body is None:  # 抽象メソッド・インターフェースの宣言
            return Lookup(True, -1)
        return Lookup(True, len(_ASSERT_CALL.findall(body)))
    if not owner and re.search(rf"\b{_CLASS_DECL}\s+{re.escape(name)}\b", code):
        return Lookup(True, -1)
    return Lookup(False)


_GENERATED_TEST = re.compile(r"@(?:ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b")


def is_generated_test(path: Path, symbol: str) -> bool:
    """パラメータ化テストなど、1 つのメソッドが複数回実行されるテストか（JUnit 5 のアノテーションで判断）.

    Gradle の JUnit XML では、こうしたテストの実行結果の名前が「[1] 引数…」になり、メソッド名が出ない。
    結果と照合するときの手がかりに使う（Python の parametrize は結果の名前にメソッド名が残るので対象外）。
    """
    if path.suffix == ".py":
        return False
    code = _strip_comments_and_strings(path.read_text(encoding="utf-8", errors="replace"))
    owner, name = split_symbol(symbol)
    start = 0
    if owner:
        m = re.search(rf"\b{_CLASS_DECL}\s+{re.escape(owner)}\b", code)
        if not m:
            return False
        start = m.end()
    for m in re.finditer(rf"\b{re.escape(name)}[ \t]*\(", code[start:]):
        pos = start + m.start()
        before = code[:pos].rstrip()
        if not before or not (before[-1].isalnum() or before[-1] in "_>]"):
            continue  # 宣言ではなく呼び出し（直前が型名でない: obj.name( / = name( など）
        if re.search(r"\b(?:return|new|throw)$", before):
            continue
        # メソッド名から前へ戻り、直前のメンバーの終わり（かっこの外の ; { }）までを宣言の頭（アノテーション）とみなす
        depth = 0
        i = pos - 1
        while i >= 0:
            c = code[i]
            if c == ")":
                depth += 1
            elif c == "(":
                depth -= 1
            elif c in ";{}" and depth == 0:
                break
            i -= 1
        return bool(_GENERATED_TEST.search(code[i + 1 : pos]))
    return False


def lookup_symbol(path: Path, symbol: str) -> Lookup:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return _py_lookup(text, symbol)
    return _generic_lookup(text, symbol)


# --- Gherkin（.feature）---------------------------------------------------

_SCENARIO = re.compile(r"^\s*(?:Scenario(?: Outline)?|Example|シナリオ(?:アウトライン)?)\s*:\s*(.*?)\s*$")
_FEATURE = re.compile(r"^\s*(?:Feature|機能|フィーチャ)\s*:")
_IGNORE_TAGS = {"@ignore", "@skip", "@wip", "@disabled"}
_TAGS = re.compile(r"^\s*@")
_THEN = re.compile(r"^\s*(?:Then|And|But|\*|ならば|かつ|しかし)\s+")
_KARATE_ASSERT = re.compile(r"^\s*(?:\*|Then|And)\s+(?:match|assert|status)\b")


@dataclass
class ScenarioInfo:
    found: bool
    ignored: bool = False
    checks: int = 0


def _tags_above(lines: list[str], i: int) -> list[str]:
    """i 行目（Feature: / Scenario: など）の直前に書かれたタグ（空行・コメント行は飛ばす）."""
    tags: list[str] = []
    j = i - 1
    while j >= 0 and (_TAGS.match(lines[j]) or not lines[j].strip() or lines[j].lstrip().startswith("#")):
        if _TAGS.match(lines[j]):
            tags += lines[j].split()
        j -= 1
    return tags


def lookup_scenario(path: Path, scenario: str) -> ScenarioInfo:
    """シナリオを探す. Feature 全体に付いたタグ（@ignore など）もシナリオに効くので、両方を見る."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    feature_tags: list[str] = []
    for i, line in enumerate(lines):
        if _FEATURE.match(line):
            feature_tags = _tags_above(lines, i)
            continue
        m = _SCENARIO.match(line)
        if not m or m.group(1) != scenario:
            continue
        tags = feature_tags + _tags_above(lines, i)
        checks = 0
        seen_then = False
        for body in lines[i + 1 :]:
            if _SCENARIO.match(body) or _TAGS.match(body):
                break
            if body.strip().startswith(("Then ", "ならば")):
                seen_then = True
            if _KARATE_ASSERT.match(body) or (seen_then and _THEN.match(body)):
                checks += 1
        return ScenarioInfo(True, ignored=any(t in _IGNORE_TAGS for t in tags), checks=checks)
    return ScenarioInfo(False)
