"""test-scaffold — Excel のテスト仕様書から JUnit 5 のテストクラスの雛形を作る（LLM を使わない決定論のツール）.

例:
  test-scaffold docs/テスト仕様書.xlsx --dry-run              # 作る予定だけ表示（書かない）
  test-scaffold docs/テスト仕様書.xlsx                        # 無いクラスだけ作る（既存ファイルは上書きしない）
  test-scaffold docs/テスト仕様書.xlsx --merge                # 既存のクラスに、無いメソッドだけ足す
  test-scaffold docs/テスト仕様書.xlsx --config scaffold.yaml --proofs-out build/proofs.yaml
  test-scaffold --print-config                               # 設定の既定値を表示

出力先（--out。既定 template/src/test/java）は --root（既定: カレント）の中だけ。
終了コード: 0 成功 / 1 警告あり（--strict のとき）/ 2 入力・設定の誤り / 3 想定外のエラー
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import __version__
from .config import default_config_yaml, load_config
from .errors import ExitCode, UsageError
from .java import TestClass, existing_keys, merge_into, missing_methods, plan_classes, render_class
from .reader import Notice, read_workbook

TOOL = "test-scaffold"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=TOOL, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("spec", nargs="?", type=Path, help="テスト仕様書（.xlsx / .xlsm）")
    p.add_argument("-c", "--config", type=Path, help="設定（YAML）。省略時は既定値（--print-config で表示）")
    p.add_argument("--root", type=Path, default=Path("."), help="リポジトリのルート（既定: .）。出力はこの中だけ")
    p.add_argument(
        "--out",
        type=Path,
        default=Path("template/src/test/java"),
        help="テストのソースの置き場（--root からの相対。既定: template/src/test/java）",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--merge", action="store_true", help="既存のクラスに、まだ無いメソッドだけ足す（差分モード）")
    mode.add_argument("--force", action="store_true", help="既存のクラスを上書きする（書いたテストが消える）")
    p.add_argument("--dry-run", action="store_true", help="作る予定だけ表示し、ファイルを書かない")
    p.add_argument("--strict", action="store_true", help="警告（要件 ID の無い行など）があれば終了コード 1")
    p.add_argument(
        "--trace",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="対応表（traceability/specs など。ファイルかディレクトリ、複数可）。無い要件 ID を警告する",
    )
    p.add_argument(
        "--proofs-out",
        type=Path,
        metavar="PATH",
        help="対応表の proofs の候補（要件 ID → file / symbol）を YAML で書く（--root の中だけ）",
    )
    p.add_argument("--print-config", action="store_true", help="設定の既定値（YAML）を表示して終わる")
    return p


@dataclass
class Action:
    test_class: TestClass
    path: Path  # --root からの相対
    verb: str  # create / overwrite / merge / unchanged / skip
    methods: list = field(default_factory=list)  # 書くメソッド
    present: list = field(default_factory=list)  # 結果のファイルにあるメソッド（proofs の候補にする）
    text: str = ""


VERBS = {
    "create": ("作成", "作成予定"),
    "overwrite": ("上書き", "上書き予定"),
    "merge": ("追加", "追加予定"),
    "unchanged": ("変更なし", "変更なし"),
    "skip": ("スキップ", "スキップ"),
}


def _inside(path: Path, base: Path, what: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise UsageError(f"{what} が {base} の外を指しています: {path}") from None
    return resolved


def _trace_ids(paths: list[Path]) -> set[str]:
    ids: set[str] = set()
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(x for x in p.rglob("*") if x.suffix in {".yaml", ".yml"})
        elif p.is_file():
            files.append(p)
        else:
            raise UsageError(f"対応表がありません: {p}")
    for f in files:
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            raise UsageError(f"対応表を YAML として読めません: {f}: {e}") from e
        for req in data.get("requirements", []) if isinstance(data, dict) else []:
            if isinstance(req, dict) and isinstance(req.get("id"), str):
                ids.add(req["id"])
    return ids


def plan(args: argparse.Namespace) -> tuple[list[Action], list[Notice], list[Notice], int]:
    if args.spec is None:
        raise UsageError(
            "テスト仕様書（.xlsx）を指定してください（例: test-scaffold docs/テスト仕様書.xlsx --dry-run）"
        )
    cfg = load_config(args.config)
    if not args.root.is_dir():
        raise UsageError(f"--root がディレクトリではありません: {args.root}")
    root = args.root.resolve()
    out = _inside(args.out if args.out.is_absolute() else root / args.out, root, "--out")

    data = read_workbook(args.spec, cfg)
    warnings = list(data.warnings)
    if args.trace:
        known = _trace_ids([t if t.is_absolute() else root / t for t in args.trace])
        for case in data.cases:
            for rid in case.requirement_ids:
                if rid not in known:
                    warnings.append(Notice(case.location, f"項番 {case.id}: 要件 ID {rid} が対応表にありません"))

    actions: list[Action] = []
    for tc in plan_classes(data.cases, cfg, root, warnings):
        target = _inside(out / tc.relpath, out, "出力先")
        rel = target.relative_to(root)
        if target.exists() and not target.is_file():
            raise UsageError(f"出力先がファイルではありません: {rel.as_posix()}")
        if not target.exists() or args.force:
            verb = "overwrite" if target.exists() else "create"
            text = render_class(tc, args.spec.name)
            actions.append(Action(tc, rel, verb, tc.methods, tc.methods, text))
            continue
        current = target.read_text(encoding="utf-8")
        if not args.merge:
            warnings.append(
                Notice(
                    rel.as_posix(),
                    "既にあるため作りませんでした（足りないメソッドだけ足すなら --merge、上書きは --force）",
                )
            )
            actions.append(Action(tc, rel, "skip"))
            continue
        todo = missing_methods(tc, current)
        names, _ = existing_keys(current)
        present = [m for m in tc.methods if m.name in names or m in todo]
        if not todo:
            actions.append(Action(tc, rel, "unchanged", [], present))
            continue
        try:
            text = merge_into(current, todo)
        except ValueError as e:
            raise UsageError(f"{rel.as_posix()}: {e}") from e
        actions.append(Action(tc, rel, "merge", todo, present, text))
    return actions, warnings, data.skipped_sheets, len(data.cases)


def proofs_yaml(actions: list[Action]) -> str:
    by_req: dict[str, list[dict[str, str]]] = {}
    for a in actions:
        for m in a.present:
            for rid in m.case.requirement_ids:
                entry = {"file": a.path.as_posix(), "symbol": f"{a.test_class.name}#{m.name}"}
                if m.case.case_type:
                    entry["type"] = m.case.case_type
                by_req.setdefault(rid, []).append(entry)
    head = (
        "# test-scaffold が作った proofs の候補（要件 ID → テスト）。テストを実装して通してから、\n"
        "# 対応表（traceability/specs/*.yaml）の該当する要件の proofs に写す。雛形のままでは D3・D7 を通らない\n"
    )
    body = yaml.safe_dump(dict(sorted(by_req.items())), allow_unicode=True, sort_keys=False) if by_req else "{}\n"
    return head + body


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_config:
        sys.stdout.write(default_config_yaml())
        return ExitCode.OK

    actions, warnings, skipped, n_cases = plan(args)
    root = args.root.resolve()
    proofs_path = None
    if args.proofs_out is not None:
        proofs_path = _inside(
            args.proofs_out if args.proofs_out.is_absolute() else root / args.proofs_out, root, "--proofs-out"
        )

    dry = 1 if args.dry_run else 0
    print(
        f"{TOOL}: {args.spec.name}（{n_cases} 件・{len(actions)} クラス）"
        + ("（--dry-run: 書きません）" if dry else "")
    )
    for a in actions:
        if not dry and a.verb in {"create", "overwrite", "merge"}:
            path = root / a.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(a.text, encoding="utf-8", newline="")
        detail = f"{len(a.methods)} メソッド" if a.methods else ""
        if a.verb == "merge":
            detail += f"（既にある {len(a.present) - len(a.methods)} 件は足さない）"
        print(f"  {VERBS[a.verb][dry]:<6} {a.path.as_posix()}  {detail}".rstrip())
        for m in a.methods:
            reqs = ", ".join(m.case.requirement_ids) or "要件 ID なし"
            print(f"      - {a.test_class.name}#{m.name}  [{reqs}]")
    if proofs_path is not None:
        if dry:
            print(f"  proofs の候補: {proofs_path.relative_to(root).as_posix()}（--dry-run のため書きません）")
        else:
            proofs_path.parent.mkdir(parents=True, exist_ok=True)
            proofs_path.write_text(proofs_yaml(actions), encoding="utf-8", newline="\n")
            print(f"  proofs の候補: {proofs_path.relative_to(root).as_posix()}")
    for s in skipped:
        print(f"飛ばしたシート: {s.location}（{s.message}）")
    if warnings:
        print(f"警告 {len(warnings)} 件:")
        for w in warnings:
            print(f"  {w.location}: {w.message}")
    return ExitCode.WARNINGS if (warnings and args.strict) else ExitCode.OK


def run_main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows のコンソールでも日本語を出す
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        return int(main(argv))
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return ExitCode.USAGE
    except SystemExit as e:  # argparse の誤り（2）・--help（0）
        return int(e.code or 0) if isinstance(e.code, int) else ExitCode.USAGE
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — 最上位で受けて終了コード 3 にする
        print(f"error: 想定外のエラー: {type(e).__name__}: {e}", file=sys.stderr)
        return ExitCode.RUNTIME


def entrypoint() -> None:
    sys.exit(run_main())


if __name__ == "__main__":
    entrypoint()
