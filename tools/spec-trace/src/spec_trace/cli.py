"""spec-trace — 仕様（要件）と実装・テストの対応表を検証する CLI.

例:
  spec-trace check traceability/                           # 定義を検査（レポートは Markdown）
  spec-trace check traceability/ --require proven -f json  # CI: 全要件がテスト済みであることを必須に
  spec-trace check traceability/ --test-results build/test-results/test   # テストが実行されて成功したことも確かめる
  spec-trace pin traceability/order-import.yaml            # 承認時点の設計書ハッシュを記録
  spec-trace schema                                        # 定義ファイルの JSON Schema を表示

パスは --root（既定: カレント）からの相対で書く。
終了コード: 0 問題なし / 1 error の指摘あり / 2 定義ファイル・引数の誤り / 3 実行時エラー
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from devtools_common import cli as common_cli
from devtools_common import report

from . import __version__
from .core import Settings, pin, run, spec_schema

TOOL = "spec-trace"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=TOOL, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="定義を検査する")
    c.add_argument("paths", nargs="+", type=Path, help="定義ファイル（YAML / JSON）またはそのディレクトリ")
    c.add_argument("--root", type=Path, default=Path("."), help="implements / proofs / source の起点（既定: .）")
    c.add_argument(
        "--require",
        choices=["implemented", "proven"],
        help="全要件にこの状態以上を求める（満たさない要件は error）",
    )
    c.add_argument("--min-asserts", type=int, default=1, help="テスト 1 件あたりに必要なアサーション数（既定 1）")
    c.add_argument(
        "--enforce-drift",
        action="store_true",
        help="設計書が見つからない場合もエラーにする（既定は警告）",
    )
    c.add_argument(
        "--test-results",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="JUnit 形式のテスト結果（ファイルかディレクトリ。複数可）。指定すると proven のテストが"
        "「実行されて成功した」ことも確かめる（例: template/build/test-results/test）",
    )
    common_cli.add_common_args(c)

    pn = sub.add_parser("pin", help="設計書の現在のハッシュを定義に記録する（承認後に人が実行）")
    pn.add_argument("paths", nargs="+", type=Path)
    pn.add_argument("--root", type=Path, default=Path("."))
    common_cli.add_common_args(pn)

    sc = sub.add_parser("schema", help="定義ファイルの JSON Schema を出力する")
    common_cli.add_common_args(sc)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common_cli.configure_from_args(args)

    if args.command == "schema":
        common_cli.write_output(json.dumps(spec_schema(), ensure_ascii=False, indent=2) + "\n", args.output)
        return common_cli.ExitCode.OK

    if args.command == "pin":
        from .core import collect_specs

        for p in collect_specs(args.paths):
            digest = pin(p, args.root)
            print(f"{p.as_posix()}: source_sha256 = {digest}")
        return common_cli.ExitCode.OK

    if args.min_asserts < 0:
        raise common_cli.UsageError("--min-asserts は 0 以上")
    st = Settings(
        root=args.root,
        min_asserts=args.min_asserts,
        require=args.require,
        enforce_drift=args.enforce_drift,
        test_results=args.test_results,
    )
    findings, summary = run(args.paths, st)
    text = report.render(
        findings,
        args.format,
        title="spec-trace レポート",
        meta=summary.as_meta(),
        tool=TOOL,
        tool_version=__version__,
    )
    common_cli.write_output(text, args.output)
    return common_cli.ExitCode.FINDINGS if report.has_errors(findings) else common_cli.ExitCode.OK


def entrypoint() -> None:
    sys.exit(common_cli.run_main(main))


if __name__ == "__main__":
    entrypoint()
