"""設定（YAML）の読み込みと検証.

設定はすべて省略でき、省略した項目は DEFAULTS の値になる。知らないキー・型の誤りは UsageError（終了コード 2）。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import UsageError

# 列の論理名 → 見出しの候補（比べるときは NFKC・空白除去・大文字小文字を無視）
DEFAULT_COLUMNS: dict[str, list[str]] = {
    "id": ["項番", "No", "No.", "テストNo", "ケースNo"],
    "target_class": ["テスト対象クラス", "対象クラス", "クラス"],
    "target_method": ["テスト対象メソッド", "対象メソッド", "メソッド"],
    "requirement_id": ["要件ID", "要件番号"],
    "viewpoint": ["観点", "テスト観点", "確認観点"],
    "case_type": ["種別", "区分", "テスト種別"],
    "precondition": ["前提", "前提条件"],
    "input": ["入力", "入力値", "入力データ", "手順"],
    "expected": ["期待結果", "期待値", "予想結果"],
}
# 見出しが見つからないとエラーにする列（それ以外は無ければ空として扱う）
REQUIRED_COLUMNS = ("id", "target_class", "viewpoint")

DEFAULTS: dict[str, Any] = {
    "sheets": [],
    "header_row": "auto",
    "header_search_rows": 20,
    "columns": DEFAULT_COLUMNS,
    "requirement_id_pattern": r"^REQ-[A-Z0-9]+-\d{3}$",
    "case_types": {"正常系": "normal", "異常系": "abnormal", "境界値": "boundary"},
    "java": {
        "package": "com.example.app",
        "main_source": "template/src/main/java",
        "test_class_suffix": "Test",
    },
}

_JAVA_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_PACKAGE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")
_COLUMN_LETTER = re.compile(r"^[A-Z]{1,3}$")


def normalize_header(text: object) -> str:
    """見出しの比較用: NFKC・空白（全角も）除去・小文字."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"\s+", "", s).casefold()


def column_index(letter: str) -> int:
    """'A' → 1、'AA' → 27."""
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


@dataclass
class ColumnSpec:
    headers: list[str] = field(default_factory=list)  # 見出しの候補
    letter: str | None = None  # 列記号で直接指定したとき


@dataclass
class Config:
    sheets: list[str]
    header_row: int | None  # None は自動
    header_search_rows: int
    columns: dict[str, ColumnSpec]
    requirement_id_pattern: re.Pattern[str]
    case_types: dict[str, str]
    package: str
    main_source: str
    test_class_suffix: str


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise UsageError(f"設定の誤り: {msg}")


def _column(name: str, value: Any) -> ColumnSpec:
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list):
        _expect(
            bool(value) and all(isinstance(v, str) and v.strip() for v in value),
            f"columns.{name} は見出しの文字列（またはそのリスト）か {{column: B}}"
            "（YAML では No・Yes・On・Off などは真偽値になるので 'No' のように引用符で囲む）",
        )
        return ColumnSpec(headers=list(value))
    if isinstance(value, dict):
        _expect(set(value) == {"column"}, f"columns.{name} に使えるキーは column だけです")
        letter = str(value["column"]).strip().upper()
        _expect(bool(_COLUMN_LETTER.match(letter)), f"columns.{name}.column は列記号（A〜XFD）: {value['column']!r}")
        return ColumnSpec(letter=letter)
    raise UsageError(f"設定の誤り: columns.{name} は見出しの文字列・リスト、または {{column: B}}")


def load_config(path: Path | None) -> Config:
    raw: dict[str, Any] = {}
    if path is not None:
        if not path.is_file():
            raise UsageError(f"設定ファイルがありません: {path}")
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            raise UsageError(f"設定ファイルを YAML として読めません: {path}: {e}") from e
        if loaded is None:
            loaded = {}
        _expect(isinstance(loaded, dict), "最上位はマッピング（キー: 値）にしてください")
        raw = loaded
    return build_config(raw)


def build_config(raw: dict[str, Any]) -> Config:
    unknown = set(raw) - set(DEFAULTS)
    _expect(not unknown, f"知らないキー: {', '.join(sorted(unknown))}（使えるキー: {', '.join(DEFAULTS)}）")

    sheets = raw.get("sheets", DEFAULTS["sheets"]) or []
    if isinstance(sheets, str):
        sheets = [sheets]
    _expect(isinstance(sheets, list) and all(isinstance(s, str) for s in sheets), "sheets はシート名のリスト")

    header_row = raw.get("header_row", DEFAULTS["header_row"])
    if header_row == "auto":
        header_row = None
    else:
        _expect(
            isinstance(header_row, int) and not isinstance(header_row, bool) and header_row >= 1,
            f"header_row は 1 以上の整数か auto: {header_row!r}",
        )
    search = raw.get("header_search_rows", DEFAULTS["header_search_rows"])
    _expect(
        isinstance(search, int) and not isinstance(search, bool) and search >= 1, "header_search_rows は 1 以上の整数"
    )

    cols_raw = raw.get("columns", {}) or {}
    _expect(isinstance(cols_raw, dict), "columns はマッピング（論理名: 見出し）")
    unknown_cols = set(cols_raw) - set(DEFAULT_COLUMNS)
    _expect(
        not unknown_cols, f"知らない列: {', '.join(sorted(unknown_cols))}（使える列: {', '.join(DEFAULT_COLUMNS)}）"
    )
    columns = {name: _column(name, cols_raw.get(name, default)) for name, default in DEFAULT_COLUMNS.items()}
    letters = [c.letter for c in columns.values() if c.letter]
    _expect(len(letters) == len(set(letters)), "columns で同じ列記号を 2 つ以上の列に指定しています")

    pattern = raw.get("requirement_id_pattern", DEFAULTS["requirement_id_pattern"])
    _expect(isinstance(pattern, str) and pattern, "requirement_id_pattern は正規表現の文字列")
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise UsageError(f"設定の誤り: requirement_id_pattern が正規表現として不正: {e}") from e

    case_types = raw.get("case_types", DEFAULTS["case_types"]) or {}
    _expect(
        isinstance(case_types, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in case_types.items()),
        "case_types は 文字列: 文字列 のマッピング（例 正常系: normal）",
    )

    java_raw = raw.get("java") or {}
    _expect(isinstance(java_raw, dict), "java はマッピング")
    java = {**DEFAULTS["java"], **java_raw}
    unknown_java = set(java) - set(DEFAULTS["java"])
    _expect(not unknown_java, f"java の知らないキー: {', '.join(sorted(unknown_java))}")
    _expect(
        isinstance(java["package"], str) and bool(_PACKAGE.match(java["package"])),
        f"java.package は Java のパッケージ名（小文字の英数字とドット）: {java['package']!r}",
    )
    _expect(isinstance(java["main_source"], str), "java.main_source はパス（リポジトリのルートからの相対）")
    _expect(
        isinstance(java["test_class_suffix"], str) and bool(_JAVA_IDENT.match("A" + java["test_class_suffix"])),
        "java.test_class_suffix は英数字（例 Test）",
    )
    return Config(
        sheets=sheets,
        header_row=header_row,
        header_search_rows=search,
        columns=columns,
        requirement_id_pattern=rx,
        case_types={normalize_header(k): v for k, v in case_types.items()},
        package=java["package"],
        main_source=java["main_source"],
        test_class_suffix=java["test_class_suffix"],
    )


def default_config_yaml() -> str:
    head = (
        "# test-scaffold の設定（既定値）. 変えたい項目だけ書けばよい\n"
        "# columns: 論理名 → 見出しの候補（NFKC・空白・大文字小文字を無視して比べる）\n"
        "#          列記号で指定するときは {column: C}\n"
    )
    return head + yaml.safe_dump(DEFAULTS, allow_unicode=True, sort_keys=False)
