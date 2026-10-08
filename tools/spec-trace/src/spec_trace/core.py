"""トレーサビリティ定義（spec YAML）を読み、記載された状態に実在の裏付けがあるかを検査する.

考え方:
- 「実装済み」「テスト済み」は書いた人（AI エージェントを含む）の自己申告ではなく、コードの実在で裏付ける。
  裏付けのない申告はエラーにする（存在しない関数を「実装済み」にする・中身のないテストで「テスト済み」にする、を防ぐ）。
- 設計書のハッシュを承認時に記録しておき、設計書が変わったのに定義が古いまま（ドリフト）を検知する。
- 保証するのは「存在」と「最低限のアサーション」まで。テストの意味的な妥当性は人のレビューで担保する。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema
from devtools_common.cli import UsageError
from devtools_common.config import load_structured
from devtools_common.log import get_logger
from devtools_common.report import Finding, Severity

from .code import is_generated_test, lookup_scenario, lookup_symbol, split_case, split_symbol
from .results import FAILED, SKIPPED, TestResults, load_results

log = get_logger(__name__)

STATUSES = ["pending", "implemented", "proven"]


@dataclass
class Settings:
    root: Path = Path(".")
    min_asserts: int = 1
    require: str | None = None  # 全要件にこの状態以上を求める（implemented / proven）
    enforce_drift: bool = False  # 設計書が見つからない場合もエラーにする
    test_results: list[Path] = field(default_factory=list)  # JUnit 形式の結果。指定すると「実行されて成功」も求める
    _results: TestResults | None = None

    def results(self) -> TestResults | None:
        if self.test_results and self._results is None:
            self._results = load_results(self.test_results)
        return self._results


@dataclass
class Summary:
    specs: int = 0
    requirements: int = 0
    status: Counter[str] = field(default_factory=Counter)

    def as_meta(self) -> dict[str, Any]:
        proven = self.status.get("proven", 0)
        return {
            "specs": self.specs,
            "requirements": self.requirements,
            **{s: self.status.get(s, 0) for s in STATUSES},
            "proven_ratio": f"{proven / self.requirements:.0%}" if self.requirements else "-",
        }


def spec_schema() -> dict[str, Any]:
    return json.loads(files("spec_trace").joinpath("schemas/spec.schema.json").read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    """設計書の内容ハッシュ. テキストは改行コードを LF にそろえてから計算する.

    Windows の Git（core.autocrlf）で CRLF に変わっても、内容が同じならドリフト扱いにしないため。
    """
    data = path.read_bytes()
    if b"\0" not in data[:8192]:  # テキストとみなす
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def load_spec(path: Path) -> dict[str, Any]:
    data = load_structured(path)
    errors = sorted(
        jsonschema.Draft202012Validator(spec_schema()).iter_errors(data), key=lambda e: list(e.absolute_path)
    )
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors[:5])
        raise UsageError(f"{path} の形式が不正です: {detail}")
    return data


def collect_specs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix in {".yaml", ".yml", ".json"} and f.is_file())
        elif p.is_file():
            out.append(p)
        else:
            raise UsageError(f"入力が見つかりません: {p}")
    return out


def _check_drift(spec: dict[str, Any], loc: str, st: Settings) -> list[Finding]:
    source = spec.get("source")
    if not source:
        return []
    path = st.root / source
    if not path.is_file():
        return [
            Finding(
                "trace.source_missing",
                Severity.ERROR if st.enforce_drift else Severity.WARNING,
                "根拠の設計書が見つからないため、ドリフト検知をしていません",
                location=loc,
                field="source",
                actual=source,
                suggestion="--root を設計書の置き場所に合わせる（CI で設計書が無いなら --enforce-drift を付けない）",
            )
        ]
    pinned = spec.get("source_sha256")
    if not pinned:
        return [
            Finding(
                "trace.source_unpinned",
                Severity.WARNING,
                "設計書のハッシュが未記録です（設計書が変わっても検知できません）",
                location=loc,
                field="source_sha256",
                suggestion=f"承認後に spec-trace pin {loc} で記録する",
            )
        ]
    current = sha256_of(path)
    if current != pinned:
        return [
            Finding(
                "trace.spec_drift",
                Severity.ERROR,
                "設計書が承認時から変わっています。実装・テスト・この定義の見直しが必要です",
                location=loc,
                field="source_sha256",
                expected=pinned,
                actual=current,
                suggestion="差分を確認して要件を更新し、レビュー後に spec-trace pin で記録し直す",
            )
        ]
    return []


def _check_implements(req: dict[str, Any], loc: str, st: Settings) -> list[Finding]:
    out: list[Finding] = []
    items = req.get("implements") or []
    if not items:
        return [
            Finding(
                "trace.implements_empty",
                Severity.ERROR,
                f"状態が {req['status']} なのに実装箇所（implements）が書かれていません",
                location=loc,
                field="implements",
                suggestion="実装したファイルと関数を implements に書くか、状態を pending に戻す",
            )
        ]
    for it in items:
        path = st.root / it["file"]
        if not path.is_file():
            out.append(
                Finding(
                    "trace.implements_missing",
                    Severity.ERROR,
                    "実装ファイルが存在しません",
                    location=loc,
                    field="implements.file",
                    actual=it["file"],
                    suggestion="パス（--root からの相対）を確認する",
                )
            )
            continue
        symbol = it.get("symbol")
        if symbol and not lookup_symbol(path, symbol).found:
            out.append(
                Finding(
                    "trace.implements_missing",
                    Severity.ERROR,
                    f"実装ファイルに {symbol} が見つかりません",
                    location=loc,
                    field="implements.symbol",
                    actual=f"{it['file']} {symbol}",
                    suggestion="名前の変更・削除がないか確認し、定義を更新する",
                )
            )
    return out


def _check_proofs(req: dict[str, Any], loc: str, st: Settings) -> list[Finding]:
    out: list[Finding] = []
    items = req.get("proofs") or []
    if not items:
        return [
            Finding(
                "trace.proofs_empty",
                Severity.ERROR,
                "状態が proven なのにテスト（proofs）が書かれていません",
                location=loc,
                field="proofs",
                suggestion="この要件を確かめるテストを proofs に書くか、状態を implemented に戻す",
            )
        ]
    for it in items:
        path = st.root / it["file"]
        if not path.is_file():
            out.append(
                Finding(
                    "trace.proof_missing",
                    Severity.ERROR,
                    "テストファイルが存在しません",
                    location=loc,
                    field="proofs.file",
                    actual=it["file"],
                )
            )
            continue
        if path.suffix == ".feature" or it.get("scenario"):
            name = it.get("scenario", "")
            sc = lookup_scenario(path, name)
            if not sc.found:
                out.append(
                    Finding(
                        "trace.proof_missing",
                        Severity.ERROR,
                        f"シナリオ「{name}」が見つかりません",
                        location=loc,
                        field="proofs.scenario",
                        actual=it["file"],
                    )
                )
            elif sc.ignored:
                out.append(
                    Finding(
                        "trace.proof_ignored",
                        Severity.ERROR,
                        f"シナリオ「{name}」が @ignore 等で無効化されています",
                        location=loc,
                        field="proofs.scenario",
                        suggestion="無効化を外すか、状態を implemented に戻す",
                    )
                )
            elif sc.checks < st.min_asserts:
                out.append(
                    Finding(
                        "trace.proof_no_assert",
                        Severity.ERROR,
                        f"シナリオ「{name}」に結果の確認（Then / match / assert）がありません",
                        location=loc,
                        field="proofs.scenario",
                        expected=f">= {st.min_asserts}",
                        actual=str(sc.checks),
                    )
                )
            elif st.results() is not None:
                out.append(
                    Finding(
                        "trace.proof_result_unchecked",
                        Severity.WARNING,
                        f"シナリオ「{name}」は実行結果を照合していません（存在と結果の確認の有無だけを見ています）",
                        location=loc,
                        field="proofs.scenario",
                        actual=it["file"],
                        suggestion="シナリオの実行結果（Karate の JUnit XML）も --test-results に渡すと照合できる",
                    )
                )
            continue
        symbol = it.get("symbol")
        if not symbol:
            # どのテストかを指していない proof は裏付けにならない（ファイルがあるだけで proven にしない）
            out.append(
                Finding(
                    "trace.proof_symbol_missing",
                    Severity.ERROR,
                    "テスト（proofs）にテスト関数（symbol）が書かれていません",
                    location=loc,
                    field="proofs.symbol",
                    actual=it["file"],
                    suggestion="テスト関数を symbol に書く（クラス名#メソッド名）。.feature なら scenario",
                )
            )
            continue
        found = lookup_symbol(path, symbol)
        if not found.found:
            out.append(
                Finding(
                    "trace.proof_missing",
                    Severity.ERROR,
                    f"テストファイルに {symbol} が見つかりません",
                    location=loc,
                    field="proofs.symbol",
                    actual=f"{it['file']} {symbol}",
                )
            )
        elif 0 <= found.asserts < st.min_asserts:
            out.append(
                Finding(
                    "trace.proof_no_assert",
                    Severity.ERROR,
                    f"テスト {symbol} に検証（assert / verify / expect 等）がありません",
                    location=loc,
                    field="proofs.symbol",
                    expected=f">= {st.min_asserts}",
                    actual=str(found.asserts),
                    suggestion="結果を確かめるアサーションを書く（実行するだけのテストは裏付けにならない）",
                )
            )
        elif st.results() is not None:
            out += _check_result(symbol, it["file"], loc, st, is_generated_test(path, symbol))
    return out


def _check_result(symbol: str, file: str, loc: str, st: Settings, generated: bool) -> list[Finding]:
    """--test-results が指定されていれば、そのテストが実行されて成功したかを確かめる."""
    results = st.results()
    if results is None:
        return []
    owner, method = split_symbol(symbol)
    cases = results.find(owner, method, generated, split_case(symbol)[1])
    if not cases:
        seen = results.names_in_class(owner)
        hint = f"（このクラスの結果にある名前: {', '.join(seen)}）" if seen else "（このクラスの結果がありません）"
        return [
            Finding(
                "trace.proof_not_run",
                Severity.ERROR,
                f"テスト {symbol} の実行結果がありません（実行されていない）{hint}",
                location=loc,
                field="proofs.symbol",
                actual=f"{file} {symbol}",
                suggestion="テストを実行してから照合する。タグなどで除外されていないか確認する",
            )
        ]
    failed = [c for c in cases if c.outcome == FAILED]
    if failed:
        return [
            Finding(
                "trace.proof_failed",
                Severity.ERROR,
                f"テスト {symbol} が失敗しています（{len(failed)} / {len(cases)} 件）",
                location=loc,
                field="proofs.symbol",
                actual=f"{failed[0].name}: {failed[0].message}",
                suggestion="テストが通るように直すか、状態を implemented に戻す",
            )
        ]
    if all(c.outcome == SKIPPED for c in cases):
        return [
            Finding(
                "trace.proof_skipped",
                Severity.ERROR,
                f"テスト {symbol} がスキップされています（実行されていない）",
                location=loc,
                field="proofs.symbol",
                actual=cases[0].message,
                suggestion="スキップを外すか、状態を implemented に戻す",
            )
        ]
    return []


def check_spec(path: Path, st: Settings, summary: Summary, seen_ids: dict[str, str]) -> list[Finding]:
    spec = load_spec(path)
    loc_base = path.name
    findings = _check_drift(spec, loc_base, st)
    summary.specs += 1
    for req in spec["requirements"]:
        rid, status = req["id"], req["status"]
        loc = f"{loc_base}#{rid}"
        summary.requirements += 1
        summary.status[status] += 1
        if rid in seen_ids:
            findings.append(
                Finding(
                    "trace.duplicate_id",
                    Severity.ERROR,
                    f"要件 ID が重複しています（{seen_ids[rid]} にもあります）",
                    location=loc,
                    field="id",
                )
            )
        seen_ids.setdefault(rid, loc_base)
        if status in ("implemented", "proven"):
            findings += _check_implements(req, loc, st)
        if status == "proven":
            findings += _check_proofs(req, loc, st)
        if st.require and STATUSES.index(status) < STATUSES.index(st.require):
            findings.append(
                Finding(
                    "trace.not_done",
                    Severity.ERROR,
                    f"状態が {status} です（{st.require} 以上が必要）",
                    location=loc,
                    field="status",
                    expected=st.require,
                    actual=status,
                )
            )
        elif status == "pending":
            findings.append(Finding("trace.pending", Severity.INFO, "未着手（pending）", location=loc, field="status"))
    return findings


def run(paths: list[Path], st: Settings) -> tuple[list[Finding], Summary]:
    summary = Summary()
    seen: dict[str, str] = {}
    findings: list[Finding] = []
    for p in collect_specs(paths):
        findings += check_spec(p, st, summary, seen)
    log.info("checked %d specs / %d requirements", summary.specs, summary.requirements)
    return findings, summary


def pin(path: Path, root: Path) -> str:
    """設計書の現在のハッシュを spec ファイルの source_sha256 に書き込む（コメント・並びは保つ）."""
    spec = load_spec(path)
    source = spec.get("source")
    if not source:
        raise UsageError(f"{path} に source（設計書のパス）がありません")
    doc = root / source
    if not doc.is_file():
        raise UsageError(f"設計書が見つかりません: {doc}")
    digest = sha256_of(doc)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_line = f'source_sha256: "{digest}"\n'
    for i, line in enumerate(lines):
        if line.startswith("source_sha256:"):
            lines[i] = new_line
            break
    else:
        idx = next((i for i, ln in enumerate(lines) if ln.startswith("source:")), None)
        if idx is None:
            raise UsageError(f"{path}: トップレベルの source: 行が見つかりません（JSON 形式は手で追記してください）")
        lines.insert(idx + 1, new_line)
    path.write_text("".join(lines), encoding="utf-8", newline="")
    return digest
