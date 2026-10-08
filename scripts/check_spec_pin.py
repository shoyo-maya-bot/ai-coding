#!/usr/bin/env python3
"""PR で設計書の承認ハッシュ（source_sha256 = pin）が変わったら、承認のラベルを求める（CI の spec-pin）.

`spec-trace pin` は人が設計書を承認したときに実行する操作（guidelines/workflow.md の「人だけが行うこと」）。
エージェントや PR の作成者が pin を書き換えて trace.spec_drift を黙らせることを防ぐため、
PR の変更前（base）と変更後（作業ツリー）の traceability/specs を比べ、source_sha256 が変わった・増えた・消えた
対応表、pin の無いまま新しく足した対応表、または pin の対象の設計書（トップレベルの source:）を消した・差し替えた
対応表があれば、
PR に `spec-pin-approved` ラベルが付いていることを求める（ラベルは設計書を承認した人が付ける）。
source を消すと spec-trace はドリフトを検知できなくなり、別の設計書に差し替えると pin の意味が変わるため、
pin と同じ扱いにする。

ラベルは GitHub が渡す PR のイベント（GITHUB_EVENT_PATH の pull_request.labels）から読む。API は呼ばない。
ラベルを付け外しすると `pull_request` の labeled / unlabeled で再実行され、結果が更新される。

  python scripts/check_spec_pin.py --base origin/main --labels spec-pin-approved   # 手元で試す
  python scripts/check_spec_pin.py   # CI（イベントから base とラベルを読む）

終了コード: 0 問題なし（pin の変更なし、またはラベルあり）/ 1 ラベルが無い / 2 使い方・入力の誤り
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 — git を引数のリストで呼ぶだけ（シェルを通さない）
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LABEL = "spec-pin-approved"
SPECS = "traceability/specs"
SUFFIXES = (".yaml", ".yml", ".json")


class InputError(Exception):
    """使い方・入力の誤り（終了コード 2）."""


def _git(*args: str, cwd: Path) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")  # nosec B603 B607
    if res.returncode != 0:
        raise InputError(f"git {' '.join(args)} が失敗しました: {res.stderr.strip()}")
    return res.stdout


Pin = tuple[str | None, str | None]  # (source = 設計書のパス, source_sha256)


def _pin_of(text: str, name: str) -> Pin:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise InputError(f"{name} を YAML として読めません: {e}") from None
    if not isinstance(data, dict):
        return (None, None)
    source, pin = data.get("source"), data.get("source_sha256")
    return (str(source) if source else None, str(pin) if pin is not None else None)


def pins_at_base(base: str, specs: str, cwd: Path) -> dict[str, Pin]:
    """base のコミットにある対応表ごとの (source, source_sha256)（無ければ None）."""
    out: dict[str, Pin] = {}
    listing = _git("ls-tree", "-r", "--name-only", base, "--", specs, cwd=cwd)
    for path in listing.splitlines():
        if path.endswith(SUFFIXES):
            out[path] = _pin_of(_git("show", f"{base}:{path}", cwd=cwd), f"{base}:{path}")
    return out


def pins_in_tree(specs: str, cwd: Path) -> dict[str, Pin]:
    """作業ツリー（PR の変更後）の対応表ごとの (source, source_sha256)."""
    out: dict[str, Pin] = {}
    root = cwd / specs
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in SUFFIXES:
            rel = p.relative_to(cwd).as_posix()
            out[rel] = _pin_of(p.read_text(encoding="utf-8"), rel)
    return out


def pin_changes(before: dict[str, Pin], after: dict[str, Pin]) -> list[str]:
    """pin（と pin の対象の設計書 source）が変わった対応表の説明（変わっていなければ空）.

    新しい対応表に pin がある・pin のある対応表を消した、も変更とみなす。
    pin の無い対応表を新しく足した、も承認が要る変更とみなす（承認されていない設計書を根拠に要件を進めないため）。
    source の行を消した・別の設計書に差し替えた、も変更とみなす（ドリフトの検知が外れる・pin の意味が変わる）。
    """
    changes = []
    for path in sorted(set(before) | set(after)):
        old_src, old = before.get(path, (None, None))
        new_src, new = after.get(path, (None, None))
        if path in before and path in after and old_src != new_src:
            if new_src is None:
                changes.append(f"{path}: 設計書（source）を削除（{old_src}）. ドリフトを検知できなくなります")
            elif old_src is None:
                changes.append(f"{path}: 設計書（source）を記録（{new_src}）")
            else:
                changes.append(f"{path}: 設計書（source）を変更（{old_src} → {new_src}）")
        if path not in before and new is None:
            changes.append(f"{path}: pin なしで追加（設計書の承認が未記録. 承認して pin するか、承認済みならラベル）")
            continue
        if old == new:
            continue
        if path not in before:
            changes.append(f"{path}: pin 付きで追加（{new}）")
        elif path not in after:
            changes.append(f"{path}: pin 付きの対応表を削除（{old}）")
        elif new is None:
            changes.append(f"{path}: pin を削除（{old}）")
        elif old is None:
            changes.append(f"{path}: pin を記録（{new}）")
        else:
            changes.append(f"{path}: pin を変更（{old} → {new}）")
    return changes


def read_event(path: str | None) -> dict:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"イベントのファイル {path} を読めません: {e}") from None


def labels_from_event(event: dict) -> set[str]:
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        raise InputError(
            "pull_request のイベントではありません（--labels でラベルを渡すか、pull_request のワークフローで実行する）"
        )
    return {str(lb.get("name", "")) for lb in pr.get("labels") or [] if isinstance(lb, dict)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="比べる元のコミット（既定: イベントの pull_request.base.sha）")
    ap.add_argument("--labels", help="PR のラベル（カンマ区切り. 指定するとイベントを読まない. 手元で試すとき）")
    ap.add_argument(
        "--event", default=os.environ.get("GITHUB_EVENT_PATH"), help="イベントの JSON（既定: GITHUB_EVENT_PATH）"
    )
    ap.add_argument("--root", type=Path, default=ROOT, help="リポジトリのルート")
    ap.add_argument("--specs", default=SPECS, help=f"対応表のフォルダ（既定: {SPECS}）")
    ap.add_argument("--label", default=LABEL, help=f"承認のラベル（既定: {LABEL}）")
    args = ap.parse_args(argv)
    try:
        event = {} if args.labels is not None and args.base else read_event(args.event)
        base = args.base or ((event.get("pull_request") or {}).get("base") or {}).get("sha")
        if not base:
            raise InputError(
                "比べる元のコミットが分かりません（--base を指定するか、pull_request のイベントで実行する）"
            )
        labels = (
            {s.strip() for s in args.labels.split(",") if s.strip()}
            if args.labels is not None
            else labels_from_event(event)
        )
        changes = pin_changes(pins_at_base(base, args.specs, args.root), pins_in_tree(args.specs, args.root))
    except InputError as e:
        print(f"::error::spec-pin: {e}")
        return 2
    if not changes:
        print(f"OK: 設計書の承認ハッシュ（source_sha256）の変更はありません（{args.specs}、比較元 {base[:12]}）")
        return 0
    print("設計書の承認ハッシュ（source_sha256）が変わっています:")
    for c in changes:
        print(f"  - {c}")
    if args.label in labels:
        print(f"OK: PR に {args.label} ラベルがあります（設計書の承認済み）")
        return 0
    print(
        "::error::spec-pin: 設計書の承認ハッシュ（source_sha256）の変更には、"
        f"設計書を承認した人が PR に「{args.label}」ラベルを付ける必要があります。"
        "pin は人が承認後に行う操作です（guidelines/workflow.md の「人だけが行うこと」）。"
        "承認していない変更なら pin を元に戻してください"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
