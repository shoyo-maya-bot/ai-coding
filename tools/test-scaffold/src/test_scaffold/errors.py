"""終了コードと、利用者が直せる誤り."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0  # 成功（--strict でなければ警告があっても 0）
    WARNINGS = 1  # --strict のとき、警告がある（要件 ID の無い行など）
    USAGE = 2  # 入力・設定・引数の誤り（Excel が読めない・見出しが無い・出力先が外に出る など）
    RUNTIME = 3  # 想定外のエラー


class UsageError(Exception):
    """入力・設定・引数の誤り（終了コード 2）."""
