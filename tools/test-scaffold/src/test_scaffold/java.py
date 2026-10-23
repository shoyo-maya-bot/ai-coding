"""テストケースから JUnit 5 のテストクラスの雛形（ソース）を作る.

- テスト対象クラスごとに 1 クラス（<対象クラス><接尾辞>。既定は MemberServiceTest）
- メソッド名は Java の識別子として安全な ASCII だけで作る（<対象メソッド>_case<項番>。日本語の観点は @DisplayName へ）
  Checkstyle の MethodName（^[a-z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)*$）に合う形にする
- 本体は fail("未実装: <項番>")。雛形のままでは D3（単体テスト）が失敗し、対応表を proven にしても D7
  （--test-results の照合）で trace.proof_failed になる。@Disabled は使わない（guidelines の禁止事項）
- コメント・文字列は 1 行 120 文字（Checkstyle の LineLength）に収まるよう折り返し、タブは空白に、
  バックスラッシュは二重にする（Java はコメントの中の \\u000a も改行として解釈するため）
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .reader import Case, Notice

MAX_LINE = 120
INDENT = "    "
FAIL_IMPORT = "import static org.junit.jupiter.api.Assertions.fail;"
TEST_IMPORT = "import org.junit.jupiter.api.Test;"
DISPLAY_NAME_IMPORT = "import org.junit.jupiter.api.DisplayName;"

_TYPE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_PACKAGE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")
_METHOD = re.compile(r"^[a-z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)*$")
_MARKER = re.compile(r"^\s*//\s*項番:\s*(.*)（シート:\s*(.*)）\s*$")
_METHOD_DECL = re.compile(r"\bvoid\s+([A-Za-z_$][\w$]*)\s*\(")
_JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue",
    "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if",
    "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private",
    "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
    "throw", "throws", "transient", "try", "void", "volatile", "while", "true", "false", "null", "var", "record",
    "yield", "sealed", "permits",
}  # fmt: skip


@dataclass
class Method:
    name: str
    case: Case

    @property
    def key(self) -> tuple[str, str]:
        return (self.case.id, self.case.sheet)


@dataclass
class TestClass:
    package: str
    target: str  # テスト対象クラスの単純名
    name: str  # テストクラス名
    methods: list[Method] = field(default_factory=list)

    @property
    def relpath(self) -> Path:
        return Path(*self.package.split("."), f"{self.name}.java")

    @property
    def symbol_owner(self) -> str:
        return self.name


def java_len(text: str) -> int:
    """Checkstyle が数える長さ（UTF-16 の単位）."""
    return len(text.encode("utf-16-le")) // 2


def _safe_comment(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("\t", "    ").replace("\r", "")
    return "".join(" " if (ord(ch) < 0x20 and ch != "\n") or ord(ch) == 0x7F else ch for ch in text)


def java_string(text: str) -> str:
    """Java の文字列リテラルの中身（ダブルクォートなし）."""
    out = []
    for ch in text.replace("\r\n", "\n"):
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:  # 改行・タブなどの制御文字は空白に（表示名は 1 行）
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _chunks(text: str, width: int) -> list[str]:
    """UTF-16 の長さで width 以下に切る（エスケープ \\x の途中では切らない）."""
    parts, cur, n = [], "", 0
    i = 0
    while i < len(text):
        piece = text[i : i + 2] if text[i] == "\\" else text[i]
        w = java_len(piece)
        if cur and n + w > width:
            parts.append(cur)
            cur, n = "", 0
        cur += piece
        n += w
        i += len(piece)
    if cur or not parts:
        parts.append(cur)
    return parts


def _identifier_part(text: str) -> str:
    """ASCII の英数字だけを残し、それ以外は _ でつなぐ（'1-2' → '1_2'、'No.3' → 'No_3'）."""
    return "_".join(re.findall(r"[A-Za-z0-9]+", unicodedata.normalize("NFKC", text)))


def method_base(case: Case) -> str:
    base = case.target_method.split("(")[0].strip()
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", base or "-") or not base.isascii():
        return ""
    base = _identifier_part(base)
    return base[:1].lower() + base[1:] if base else ""


def method_name(case: Case) -> str:
    base = method_base(case)
    part = _identifier_part(case.id) or f"R{case.row}"
    name = f"{base}_case{part}" if base else f"case{part}"
    if not _METHOD.match(name):  # 例: 対象メソッドが数字で始まる・_ だけ
        name = f"case{part}"
    if not _METHOD.match(name) or name in _JAVA_KEYWORDS:
        name = f"caseR{case.row}"
    return name


def _resolve_package(target: str, cfg: Config, root: Path, warnings: list[Notice], loc: str) -> tuple[str, str] | None:
    """'com.example.app.member.MemberService' / 'MemberService' → (パッケージ, 単純名)."""
    target = target.strip()
    if "." in target:
        pkg, _, simple = target.rpartition(".")
        if not _PACKAGE.match(pkg):
            warnings.append(Notice(loc, f"パッケージ名として使えません: {pkg}（この行は飛ばしました）"))
            return None
    else:
        pkg, simple = "", target
    if not _TYPE_NAME.match(simple):
        warnings.append(
            Notice(
                loc,
                f"テスト対象クラス名が Java のクラス名（英大文字で始まる英数字）ではありません: {target}"
                "（飛ばしました）",
            )
        )
        return None
    if pkg:
        return pkg, simple
    main = root / cfg.main_source
    if main.is_dir():
        hits = sorted(p for p in main.rglob(f"{simple}.java") if p.is_file())
        if len(hits) == 1:
            rel = hits[0].parent.relative_to(main)
            found = ".".join(rel.parts)
            if found and _PACKAGE.match(found):
                return found, simple
        reason = "見つかりません" if not hits else f"{len(hits)} か所にあります"
        warnings.append(
            Notice(loc, f"{simple}.java が {cfg.main_source} に{reason}。java.package（{cfg.package}）に置きます")
        )
    return cfg.package, simple


def plan_classes(cases: list[Case], cfg: Config, root: Path, warnings: list[Notice]) -> list[TestClass]:
    classes: dict[tuple[str, str], TestClass] = {}
    resolved: dict[str, tuple[str, str] | None] = {}
    for case in cases:
        if case.target_class not in resolved:
            resolved[case.target_class] = _resolve_package(case.target_class, cfg, root, warnings, case.location)
        pkg_simple = resolved[case.target_class]
        if pkg_simple is None:
            continue
        pkg, simple = pkg_simple
        tc = classes.setdefault((pkg, simple), TestClass(pkg, simple, f"{simple}{cfg.test_class_suffix}"))
        if any(m.key == (case.id, case.sheet) for m in tc.methods):
            warnings.append(Notice(case.location, f"項番 {case.id} が同じシート・同じクラスで重複しています"))
        name = method_name(case)
        used = {m.name for m in tc.methods}
        if name in used:
            n = 2
            while f"{name}_{n}" in used:
                n += 1
            name = f"{name}_{n}"
        tc.methods.append(Method(name, case))
    return sorted(classes.values(), key=lambda c: (c.package, c.name))


# --- 描画 -------------------------------------------------------------------


def _comment_lines(label: str, value: str, indent: str) -> list[str]:
    prefix = f"{indent}// {label}: "
    cont = f"{indent}//   "
    out: list[str] = []
    lines = _safe_comment(value).split("\n") if value else [""]
    for i, line in enumerate(lines):
        head = prefix if i == 0 else cont
        # 1 片目は head の後ろ、2 片目以降は cont の後ろ. cont の方が短いので、head の幅で切れば両方に収まる
        for j, chunk in enumerate(_chunks(line, MAX_LINE - java_len(head))):
            out.append(((head if j == 0 else cont) + chunk).rstrip())
    return out


def _display_name(text: str, indent: str) -> list[str]:
    lit = java_string(text)
    first_width = MAX_LINE - java_len(f'{indent}@DisplayName("') - 1
    if java_len(lit) <= first_width - 1:
        return [f'{indent}@DisplayName("{lit}")']
    cont_indent = indent + INDENT * 2
    chunks = _chunks(lit, first_width - 2)
    rest = _chunks("".join(chunks[1:]), MAX_LINE - java_len(f'{cont_indent}+ "') - 3)
    out = [f'{indent}@DisplayName("{chunks[0]}"']
    for k, c in enumerate(rest):
        out.append(f'{cont_indent}+ "{c}"' + (")" if k == len(rest) - 1 else ""))
    return out


def render_method(m: Method) -> list[str]:
    c = m.case
    i1, i2 = INDENT, INDENT * 2
    lines = [f"{i1}// 項番: {_safe_comment(c.id)}（シート: {_safe_comment(c.sheet)}）"]
    lines += _comment_lines("要件 ID", ", ".join(c.requirement_ids) or "（なし）", i1)
    lines += _comment_lines("観点", c.viewpoint, i1)
    lines += _comment_lines("前提", c.precondition, i1)
    lines += _comment_lines("入力", c.input, i1)
    lines += _comment_lines("期待結果", c.expected, i1)
    display = f"{c.id} {c.viewpoint}".strip()
    lines += [f"{i1}@Test", *_display_name(display, i1), f"{i1}void {m.name}() {{"]
    lines += _fail_call(c.id, i2)
    lines += [f"{i1}}}"]
    return lines


def _fail_call(case_id: str, indent: str) -> list[str]:
    lit = java_string(f"未実装: {case_id}")
    one = f'{indent}fail("{lit}");'
    if java_len(one) <= MAX_LINE:
        return [one]
    cont = indent + INDENT * 2
    chunks = _chunks(lit, MAX_LINE - java_len(f'{cont}+ "') - 3)
    out = [f'{indent}fail("{chunks[0]}"']
    for k, ch in enumerate(chunks[1:]):
        out.append(f'{cont}+ "{ch}"' + (");" if k == len(chunks) - 2 else ""))
    if len(chunks) == 1:
        out[0] += ");"
    return out


def render_class(tc: TestClass, source_name: str) -> str:
    src = _safe_comment(source_name)
    lines = [
        f"package {tc.package};",
        "",
        FAIL_IMPORT,
        "",
        DISPLAY_NAME_IMPORT,
        TEST_IMPORT,
        "",
        "/**",
        f" * {tc.target} のテスト（test-scaffold がテスト仕様書 {src} から作った雛形）.",
        " *",
        " * <p>各テストは fail で失敗する。期待結果を設計書で確かめて本体を書き、対応表の proofs に",
        f" * {tc.name}#メソッド名 で記録する（雛形のままでは D3・D7 を通らない）.",
        " */",
        f"class {tc.name} {{",
    ]
    for k, m in enumerate(tc.methods):
        if k:
            lines.append("")
        lines += render_method(m)
    lines.append("}")
    return "\n".join(_wrap_doc(line) for line in lines) + "\n"


def _wrap_doc(line: str) -> str:
    """Javadoc の 1 行が長すぎる（ファイル名が長い）ときは折り返す."""
    if java_len(line) <= MAX_LINE or not line.startswith(" * "):
        return line
    return "\n".join(" * " + c for c in _chunks(line[3:], MAX_LINE - 3))


# --- 差分モード -------------------------------------------------------------


def existing_keys(text: str) -> tuple[set[str], set[tuple[str, str]]]:
    """既存のソースにあるメソッド名と、雛形の目印（// 項番: X（シート: S））."""
    names = set(_METHOD_DECL.findall(text))
    markers = set()
    for line in text.splitlines():
        m = _MARKER.match(line)
        if m:
            markers.add((m.group(1).strip(), m.group(2).strip()))
    return names, markers


_COMMENT_LABEL = re.compile(r"^\s*//\s*([^\s:：][^:：]*):\s")
_COMMENT_CONT = re.compile(r"^\s*//\s{3}")


@dataclass
class ExistingMethod:
    name: str
    marker: tuple[str, str] | None  # 直前の雛形の目印（項番, シート）
    viewpoint: tuple[str, ...] | None  # 直前の「// 観点: …」の行（前後の空白を除く）


def existing_methods(text: str) -> list[ExistingMethod]:
    """既存のソースのメソッドと、その直前（前のメソッドより後ろ）にある雛形の目印・観点のコメント."""
    out: list[ExistingMethod] = []
    marker: tuple[str, str] | None = None
    viewpoint: list[str] | None = None
    in_viewpoint = False
    for line in text.splitlines():
        m = _MARKER.match(line)
        if m:
            marker, viewpoint, in_viewpoint = (m.group(1).strip(), m.group(2).strip()), None, False
            continue
        label = _COMMENT_LABEL.match(line)
        if label and not _COMMENT_CONT.match(line):
            in_viewpoint = label.group(1).strip() == "観点"
            if in_viewpoint:
                viewpoint = [line.strip()]
            continue
        if in_viewpoint and viewpoint is not None and _COMMENT_CONT.match(line):
            viewpoint.append(line.strip())
            continue
        in_viewpoint = False
        for name in _METHOD_DECL.findall(line):
            out.append(ExistingMethod(name, marker, tuple(viewpoint) if viewpoint is not None else None))
            marker, viewpoint = None, None
    return out


def _viewpoint_lines(case: Case) -> tuple[str, ...]:
    return tuple(line.strip() for line in _comment_lines("観点", case.viewpoint, INDENT))


@dataclass
class MergePlan:
    todo: list[Method]  # 足すメソッド
    present: list[Method]  # 結果のファイルにあるメソッド（既存のものは既存の名前で。proofs の候補にする）
    notices: list[str]


def plan_merge(tc: TestClass, text: str) -> MergePlan:
    """差分モードで足すメソッドを決める（名前だけでは照合しない）.

    1. 雛形の目印のあるメソッドは、シートと観点（// 観点: のコメント）が同じなら同じケースとみなす.
       項番を振り直した仕様書でも、内容で古いメソッドに対応づける（目印の項番が違えば警告）
    2. 目印の項番・シートが同じでも観点が違うメソッドは別のケースとみなし、新しいメソッドを別名で足して警告する
       （観点のコメントを消したメソッドは、目印の項番で対応づける）
    3. 目印の無いメソッド（目印を消して実装したテスト）は名前で照合する. 同じ名前のメソッドが別の項番の目印を
       持っていれば、別名で足して警告する
    """
    existing = existing_methods(text)
    _, markers = existing_keys(text)
    names = {e.name for e in existing}
    used = set(names)
    keys = {id(m): (_safe_comment(m.case.id).strip(), _safe_comment(m.case.sheet).strip()) for m in tc.methods}
    claimed: dict[int, ExistingMethod] = {}

    # 1. 内容（シート + 観点）で対応づける. 同じ項番のものを先に
    taken: set[int] = set()
    for same_id in (True, False):
        for m in tc.methods:
            if id(m) in claimed:
                continue
            key, vp = keys[id(m)], _viewpoint_lines(m.case)
            for e in existing:
                if (
                    id(e) not in taken
                    and e.marker is not None
                    and e.viewpoint == vp
                    and e.marker[1] == key[1]
                    and (e.marker[0] == key[0]) == same_id
                ):
                    claimed[id(m)] = e
                    taken.add(id(e))
                    break

    todo: list[Method] = []
    present: list[Method] = []
    notices: list[str] = []

    def keys_of(m: Method) -> str:
        k = keys.get(id(m), ("", ""))
        return f"{k[0]}（シート: {k[1]}）"

    def add(m: Method, why: str | None) -> None:
        label = keys_of(m)
        if m.name in used:
            n = 2
            while f"{m.name}_{n}" in used:
                n += 1
            m = Method(f"{m.name}_{n}", m.case)
        if why:
            notices.append(f"{why}。項番 {label} は {m.name} として足しました（項番の振り直しを確かめてください）")
        used.add(m.name)
        todo.append(m)
        present.append(m)

    for m in tc.methods:
        key = keys[id(m)]
        e = claimed.get(id(m))
        if e is not None:
            present.append(Method(e.name, m.case))
            if e.marker != key:
                notices.append(
                    f"項番 {key[0]}（シート: {key[1]}）は、観点が同じ {e.name}（目印は項番 {e.marker[0]}）と"
                    "同じケースとみなしました。目印の項番を直してください"
                )
            continue
        same = [x for x in existing if x.marker == key and id(x) not in taken]
        if same:
            x = same[0]
            if x.viewpoint is None:  # 観点のコメントを消したメソッドは目印の項番で対応づける
                taken.add(id(x))
                present.append(Method(x.name, m.case))
            else:
                add(m, f"{x.name} は項番 {key[0]} の目印付きですが観点が違います")
            continue
        if key in markers and not any(x.marker == key for x in existing):
            continue  # 目印はあるが、その後ろにメソッドが無い（足さない。proofs の候補にもしない）
        by_name = [x for x in existing if x.name == m.name]
        if by_name:
            x = by_name[0]
            if x.marker is None or (x.marker == key and id(x) not in taken):
                taken.add(id(x))
                present.append(m)
                continue
            other = f"{x.marker[0]}（シート: {x.marker[1]}）" if x.marker else "?"
            add(m, f"{m.name} は別のケース（項番 {other}）のメソッドです")
            continue
        add(m, None)
    return MergePlan(todo, present, notices)


def missing_methods(tc: TestClass, text: str) -> list[Method]:
    """既存のソースに無いメソッドだけ（plan_merge の todo）."""
    return plan_merge(tc, text).todo


def merge_into(text: str, methods: list[Method]) -> str:
    """既存のソースの最後の } の前にメソッドを足し、足りない import を足す."""
    nl = "\r\n" if "\r\n" in text else "\n"
    body = text.replace("\r\n", "\n")
    end = body.rstrip().rfind("}")
    if end < 0:
        raise ValueError("クラスの終わり（}）が見つかりません")
    block: list[str] = []
    for m in methods:
        block.append("")
        block += render_method(m)
    head = body[:end].rstrip("\n")
    merged = head + "\n" + "\n".join(block) + "\n" + body[end:]
    merged = _ensure_imports(merged)
    if not merged.endswith("\n"):
        merged += "\n"
    return merged.replace("\n", nl)


def _ensure_imports(text: str) -> str:
    need: list[str] = []
    # 別のクラスの fail（AssertJ など）を static import 済みならそれを使う（同名の static import は衝突する）
    if not re.search(r"(?m)^import\s+static\s+[\w.]+\.(?:fail|\*)\s*;", text):
        need.append(FAIL_IMPORT)
    for imp, simple in ((DISPLAY_NAME_IMPORT, "DisplayName"), (TEST_IMPORT, "Test")):
        if not re.search(rf"(?m)^import\s+[\w.]+\.(?:{simple}|\*)\s*;", text):
            need.append(imp)
    if not need:
        return text
    lines = text.split("\n")
    statics = [i for i, ln in enumerate(lines) if ln.startswith("import static ")]
    normals = [i for i, ln in enumerate(lines) if ln.startswith("import ") and i not in statics]
    pkg = next((i for i, ln in enumerate(lines) if ln.startswith("package ")), -1)
    # 後ろから差し込む（前の位置がずれないように）. static は static の後ろ、それ以外は通常の import の後ろ
    plain = [imp for imp in need if not imp.startswith("import static ")]
    static = [imp for imp in need if imp.startswith("import static ")]
    inserts: list[tuple[int, list[str]]] = []
    if plain:
        at = normals[-1] + 1 if normals else (statics[-1] + 1 if statics else pkg + 1)
        inserts.append((at, plain if normals else ["", *plain]))
    if static:
        if statics:
            inserts.append((statics[-1] + 1, static))
        elif normals:
            inserts.append((normals[0], [*static, ""]))
        else:
            inserts.append((pkg + 1, ["", *static]))
    for at, block in sorted(inserts, key=lambda x: x[0], reverse=True):
        lines[at:at] = block
    return "\n".join(lines)
