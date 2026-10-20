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

# AssertJ・Truth の assertThat(x) は「検証の始まり」で、後ろに isEqualTo(…) などの検証の呼び出しが無いと何も確かめない。
# assertThat… の後ろのメソッドチェーンに、次の「検証ではない」呼び出し以外が 1 つも無ければ数えない
# （Hamcrest・JUnit の assertThat(actual, matcher) のように引数が 2 つ以上なら、それだけで検証）。
# assertThatThrownBy(…) は、それだけで「例外が出ること」を確かめるので対象外。
_FLUENT_START = re.compile(r"\bassertThat(?!ThrownBy\b)\w*\s*\($")
_NOT_A_CHECK = {
    "as",
    "describedAs",
    "withFailMessage",
    "overridingErrorMessage",
    "withRepresentation",
    "withThreadDumpOnError",
    "usingComparator",
    "usingElementComparator",
    "usingDefaultComparator",
    "usingRecursiveComparison",
    "usingComparatorForType",
    "usingComparatorForFields",
    "ignoringFields",
    "ignoringCase",
    "extracting",
    "extractingResultOf",
    "flatExtracting",
    "asInstanceOf",
    "asString",
    "asList",
    "withMessage",
}


def _close_paren(code: str, open_at: int) -> int:
    """code[open_at] の ( に対応する ) の位置（無ければ -1）."""
    depth = 0
    for j in range(open_at, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _has_top_level_comma(args: str) -> bool:
    depth = 0
    for ch in args:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        elif ch == "," and depth == 0:
            return True
    return False


def _fluent_has_check(code: str, open_at: int) -> bool:
    """assertThat…( の ( の位置から、引数とメソッドチェーンを読み、検証の呼び出しがあるか."""
    close = _close_paren(code, open_at)
    if close < 0:
        return False
    if _has_top_level_comma(code[open_at + 1 : close]):
        return True  # Hamcrest / JUnit の assertThat(actual, matcher)
    i = close + 1
    while True:
        m = re.match(r"\s*\.\s*(?:<[^>]*>\s*)?([A-Za-z_$][\w$]*)\s*\(", code[i:])
        if not m:
            return False
        if m.group(1) not in _NOT_A_CHECK:
            return True
        close = _close_paren(code, i + m.end() - 1)
        if close < 0:
            return False
        i = close + 1


def count_asserts(code: str) -> int:
    """（コメント・文字列を外した）コードのアサーションの数."""
    n = 0
    for m in _ASSERT_CALL.finditer(code):
        text = m.group(0)
        if _FLUENT_START.search(text) and not _fluent_has_check(code, m.end() - 1):
            continue
        n += 1
    return n


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


def _is_bare_call(region: str, m: re.Match[str], name: str) -> bool:
    """宣言らしく見えた行が、行頭から始まる複数行の呼び出し（`name(` の後で改行し `…);` で閉じる）か.

    名前の前に型・修飾子が無く（`testFoo(` だけ）、対応する ) の後が本体（{・throws・Kotlin の : / =）で
    なければ呼び出し。
    宣言とみなすと本体が無い（抽象メソッド扱い. アサーション数 -1）ことになり、検証の無いテストが D7 を素通りしていた。
    """
    open_at = m.end() - 1
    name_at = region.rfind(name, m.start(), open_at)
    if region[m.start() : name_at].strip():
        return False  # 型・修飾子・アノテーションがある: 宣言
    close = _close_paren(region, open_at)
    if close < 0:
        return False
    after = region[close + 1 :].lstrip()
    return not re.match(r"(?:\{|throws\b|:|=(?!=))", after)


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
        if _is_bare_call(region, m, name):
            continue
        body = _body_after(region, m.end())
        if body is None:  # 抽象メソッド・インターフェースの宣言
            return Lookup(True, -1)
        return Lookup(True, count_asserts(body))
    if not owner and re.search(rf"\b{_CLASS_DECL}\s+{re.escape(name)}\b", code):
        return Lookup(True, -1)
    return Lookup(False)


_GENERATED_TEST = re.compile(r"@(?:ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b")
_RESOLVED_PARAM = re.compile(r"@(?:TempDir|Mock|Autowired)\b|\b(?:TestInfo|TestReporter|RepetitionInfo)\b")


def _param_names(params: str) -> tuple[str, ...]:
    """'String line, @TempDir Path dir, Map<String, Integer> m' → ('line', 'dir', 'm')."""
    names, depth, cur = [], 0, ""
    for ch in params + ",":
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            cur = cur.strip()
            if cur:
                m = re.search(r"([A-Za-z_$][\w$]*)\s*$", cur)
                if m:
                    names.append((m.group(1), bool(_RESOLVED_PARAM.search(cur))))
            cur = ""
        else:
            cur += ch
    # JUnit の表示名（{argumentsWithNames}）に出るのは引数のソースから渡す引数だけ。
    # 拡張が渡す引数（@TempDir・TestInfo など）は後ろに置く決まりなので、最初のそれより前までを使う
    out: list[str] = []
    for name, resolved in names:
        if resolved:
            break
        out.append(name)
    return tuple(out)


def _decl_head(code: str, pos: int) -> int:
    """メソッド名の位置から前へ戻り、直前のメンバーの終わり（かっこの外の ; { }）の位置を返す.

    その次からメソッド名までが宣言の頭（アノテーション・修飾子・型）。
    """
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
    return i


def _test_methods(code: str, start: int) -> list[tuple[str, int, bool, tuple[str, ...]]]:
    """start 以降のメソッドの宣言 → [(名前, 位置, パラメータ化テストか, 引数名)]."""
    out = []
    for m in re.finditer(r"\b([A-Za-z_$][\w$]*)[ \t]*\(", code[start:]):
        name = m.group(1)
        pos = start + m.start()
        before = code[:pos].rstrip()
        if not before or not (before[-1].isalnum() or before[-1] in "_>]"):
            continue  # 宣言ではなく呼び出し（直前が型名でない: obj.name( / = name( など）
        if re.search(r"\b(?:return|new|throw|else|case)$", before) or name in {"if", "for", "while", "switch", "catch"}:
            continue
        # 引数の閉じかっこの後が { か throws でなければ宣言ではない
        open_at = start + m.end() - 1
        depth, j = 0, open_at
        while j < len(code):
            depth += code[j] == "("
            depth -= code[j] == ")"
            if depth == 0:
                break
            j += 1
        after = code[j + 1 :].lstrip()
        if not (after.startswith("{") or after.startswith("throws")):
            continue
        i = _decl_head(code, pos)
        generated = bool(_GENERATED_TEST.search(code[i + 1 : pos]))
        out.append((name, pos, generated, _param_names(code[open_at + 1 : j])))
    return out


def _class_start(code: str, owner: str | None) -> int | None:
    if not owner:
        return 0
    m = re.search(rf"\b{_CLASS_DECL}\s+{re.escape(owner)}\b", code)
    return m.end() if m else None


def generated_test_params(path: Path, symbol: str) -> tuple[str, ...] | None:
    """パラメータ化テストなど、1 つのメソッドが複数回実行されるテストなら、その引数名（ソースから渡す分）. 違えば None.

    Gradle の JUnit XML では、こうしたテストの実行結果の名前が「[1] 引数名 = 値, …」になり、メソッド名が出ない。
    結果と照合するときに、引数名の並びでどのメソッドの実行分かを見分ける（Python の parametrize は結果の名前に
    メソッド名が残るので対象外）。同じクラスに引数名の並びが同じパラメータ化テストが他にもあれば、
    結果から見分けられないので空のタプル（＝照合に使わない）を返す。
    """
    if path.suffix == ".py":
        return None
    code = _strip_comments_and_strings(path.read_text(encoding="utf-8", errors="replace"))
    owner, name = split_symbol(symbol)
    start = _class_start(code, owner)
    if start is None:
        return None
    methods = _test_methods(code, start)
    mine = next((mt for mt in methods if mt[0] == name), None)
    if mine is None or not mine[2]:
        return None
    if any(mt[2] and mt[0] != name and mt[3] == mine[3] for mt in methods):
        return ()
    return mine[3]


_DISPLAY_NAME = re.compile(r"@(?:org\.junit\.jupiter\.api\.)?DisplayName\s*\(")
_JAVA_LITERAL = re.compile(r'"((?:\\.|[^"\\\n])*)"')
_JAVA_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", "s": " ", '"': '"', "'": "'", "\\": "\\"}


def _unescape_java(text: str) -> str:
    def one(m: re.Match[str]) -> str:
        esc = m.group(1)
        if esc.startswith("u"):
            return chr(int(esc.lstrip("u"), 16))
        if esc[0] in "01234567":
            return chr(int(esc, 8))
        return _JAVA_ESCAPES.get(esc, esc)

    return re.sub(r"\\(u+[0-9a-fA-F]{4}|[0-3][0-7]{0,2}|[4-7][0-7]?|.)", one, text)


def _display_names(raw: str, code: str, start: int) -> dict[str, str | None]:
    """クラスの各メソッドの @DisplayName("…") の文字列（無い・定数を使っていて読めないものは None）."""
    out: dict[str, str | None] = {}
    for name, pos, _, _ in _test_methods(code, start):
        head_at = _decl_head(code, pos) + 1
        m = _DISPLAY_NAME.search(code[head_at:pos])
        if not m:
            out.setdefault(name, None)
            continue
        open_at = head_at + m.end() - 1
        close = _close_paren(code, open_at)
        args_raw = raw[open_at + 1 : close] if close > 0 else ""
        # 文字列リテラル（と + での連結）だけなら読む. 定数・テキストブロックは読まない
        if close < 0 or code[open_at + 1 : close].replace("+", "").strip() or '"""' in args_raw:
            out[name] = None
            continue
        out[name] = "".join(_unescape_java(x) for x in _JAVA_LITERAL.findall(args_raw))
    return out


def display_name(path: Path, symbol: str) -> str | None:
    """JUnit 5 の @DisplayName("…") が付いたテストの表示名（無ければ None）.

    Gradle の JUnit XML では、@DisplayName の付いたテストの結果の名前がメソッド名ではなく表示名になる
    （test-scaffold の雛形もこれを付ける）。結果と照合するときに、表示名でもこのメソッドの結果を探せるようにする。
    同じクラスに同じ表示名のメソッドが 2 つ以上あると結果から区別できないので None を返す（照合に使わない）。
    """
    if path.suffix == ".py":
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    code = _strip_comments_and_strings(raw)
    owner, name = split_symbol(symbol)
    start = _class_start(code, owner)
    if start is None:
        return None
    names = _display_names(raw, code, start)
    mine = names.get(name)
    if not mine or sum(1 for v in names.values() if v == mine) > 1:
        return None
    return mine


def is_generated_test(path: Path, symbol: str) -> bool:
    """パラメータ化テストなど、1 つのメソッドが複数回実行されるテストか（JUnit 5 のアノテーションで判断）."""
    return generated_test_params(path, symbol) is not None


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
