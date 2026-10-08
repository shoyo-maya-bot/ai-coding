"""template/ と dev-environment の sample-app（写し元）の差分を検査する.

template/ は dev-environment の sample-app（と local/）を写して作った雛形です。
写し元の commit と「わざと違えている箇所（理由付き）」を template/UPSTREAM.yaml に書いておき、
それ以外の差分（気づかないうちに生じたずれ）があれば失敗します。

使い方:
  python scripts/check_template_drift.py                  # UPSTREAM.yaml の sha を取得して比べる
  python scripts/check_template_drift.py --upstream-dir ../dev-environment   # 手元の checkout と比べる
  python scripts/check_template_drift.py --ref main       # sha の代わりに最新の main と比べる（固定を上げる前の確認）

UPSTREAM.yaml の形:
  repo: owner/name                # 写し元リポジトリ
  sha: <40 桁>                     # 写した時点の commit
  mappings:                       # 写し元のディレクトリ → template 内のディレクトリ
    - {upstream: sample-app, template: .}
  rename:                         # パスと中身の両方で置き換える文字列（パッケージ名など。上から順に適用）
    - {from: com.example.sample, to: com.example.app}
  ignore: [build/, .gradle/]      # 比べないパス（両側。前方一致）
  allowed_differences:            # わざと違えている箇所。reason は必須
    - path: settings.gradle       # template 側のパス
      kind: replace               # replace / modified / added / removed
      replace: [{from: "'sample-app'", to: "'app'"}]
      reason: ...

kind の意味:
  replace   写し元に replace を当てると template と完全に一致する（小さな書き換え）
  modified  中身を丸ごと違えている。keep_in_sync の正規表現に合う写し元の行は template にも同じ行が要る
            （依存ライブラリの版などは写し元に揃え続けるため）
  added     template にだけある
  removed   写し元にだけある（template には持ち込まない）

許可が不要になった（差分が無くなった、置き換え元が見つからない）エントリも失敗にします。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("replace", "modified", "added", "removed")


@dataclass
class Config:
    repo: str
    sha: str
    mappings: list[dict]
    rename: list[dict] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
    allowed: dict[str, dict] = field(default_factory=dict)


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    problems = []
    for key in ("repo", "sha", "mappings"):
        if not data.get(key):
            problems.append(f"{path.name}: {key} がありません")
    if data.get("sha") and not re.fullmatch(r"[0-9a-f]{40}", str(data["sha"])):
        problems.append(f"{path.name}: sha は 40 桁の commit ハッシュで書く（ブランチ名は不可）")
    allowed: dict[str, dict] = {}
    for i, entry in enumerate(data.get("allowed_differences") or []):
        where = f"{path.name}: allowed_differences[{i}]"
        if not entry.get("path"):
            problems.append(f"{where}: path がありません")
            continue
        if entry.get("kind") not in KINDS:
            problems.append(f"{where} ({entry['path']}): kind は {' / '.join(KINDS)} のどれか")
        if not str(entry.get("reason") or "").strip():
            problems.append(f"{where} ({entry['path']}): reason（違えている理由）がありません")
        if entry.get("kind") == "replace" and not entry.get("replace"):
            problems.append(f"{where} ({entry['path']}): kind: replace には replace の一覧が要ります")
        if entry["path"] in allowed:
            problems.append(f"{where}: {entry['path']} が重複しています")
        allowed[entry["path"]] = entry
    if problems:
        raise ValueError("\n".join(problems))
    return Config(
        repo=data["repo"],
        sha=data["sha"],
        mappings=data["mappings"],
        rename=data.get("rename") or [],
        ignore=data.get("ignore") or [],
        allowed=allowed,
    )


def apply_rename(text: str, rename: list[dict]) -> str:
    for r in rename:
        text = text.replace(r["from"], r["to"])
    return text


def ignored(rel: str, ignore: list[str]) -> bool:
    parts = rel.split("/")
    for pat in ignore:
        p = pat.rstrip("/")
        if rel == p or rel.startswith(p + "/") or (pat.endswith("/") and "/" not in p and p in parts[:-1]):
            return True
    return False


def files_under(base: Path, ignore: list[str]) -> list[str]:
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base).as_posix()
            if not ignored(rel, ignore):
                out.append(rel)
    return out


def join(prefix: str, rel: str) -> str:
    prefix = prefix.strip("/")
    return rel if prefix in ("", ".") else f"{prefix}/{rel}"


def decode(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def expected_files(upstream_root: Path, cfg: Config) -> tuple[dict[str, bytes], list[str]]:
    """写し元のファイルを template 側のパスに写像する（rename 適用済み）."""
    expected: dict[str, bytes] = {}
    problems = []
    for m in cfg.mappings:
        src = upstream_root / m["upstream"]
        if not src.is_dir():
            problems.append(f"写し元に {m['upstream']}/ がありません")
            continue
        for rel in files_under(src, cfg.ignore):
            data = (src / rel).read_bytes()
            text = decode(data)
            if text is not None:
                data = apply_rename(text, cfg.rename).encode("utf-8")
            target = join(m.get("template", "."), apply_rename(rel, cfg.rename))
            if target in expected:
                problems.append(f"{target}: 複数の写し元ファイルが同じパスに写ります")
            expected[target] = data
    return expected, problems


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def check(template_dir: Path, upstream_root: Path, cfg: Config) -> list[str]:
    expected, problems = expected_files(upstream_root, cfg)
    actual = {rel: (template_dir / rel).read_bytes() for rel in files_under(template_dir, cfg.ignore)}
    used: set[str] = set()

    for rel in sorted(set(expected) | set(actual)):
        allow = cfg.allowed.get(rel)
        kind = allow["kind"] if allow else None
        if rel not in actual:
            if kind == "removed":
                used.add(rel)
            else:
                problems.append(f"{rel}: 写し元にあるのに template にありません（写すか、kind: removed で理由を書く）")
            continue
        if rel not in expected:
            if kind == "added":
                used.add(rel)
            else:
                problems.append(f"{rel}: template にだけあります（写し元に無い。kind: added で理由を書く）")
            continue
        up, mine = expected[rel], actual[rel]
        up_text, mine_text = decode(up), decode(mine)
        same = (
            normalize(up_text) == normalize(mine_text) if up_text is not None and mine_text is not None else up == mine
        )
        if kind in ("added", "removed"):
            problems.append(f"{rel}: kind: {kind} ですが両側にあります（kind を見直す）")
            used.add(rel)
            continue
        if kind == "replace":
            used.add(rel)
            if up_text is None or mine_text is None:
                problems.append(f"{rel}: バイナリに kind: replace は使えません")
                continue
            replaced = normalize(up_text)
            for r in allow["replace"]:
                if r["from"] not in replaced:
                    problems.append(f"{rel}: 置き換え元 {r['from']!r} が写し元にありません（許可を見直す）")
                replaced = replaced.replace(r["from"], r["to"])
            if replaced != normalize(mine_text):
                problems.append(f"{rel}: 許可した置き換え以外の差分があります" + first_diff(replaced, mine_text))
            continue
        if kind == "modified":
            used.add(rel)
            if same:
                problems.append(f"{rel}: kind: modified ですが差分がありません（許可を消す）")
                continue
            if up_text is not None and mine_text is not None:
                problems += keep_in_sync(rel, up_text, mine_text, allow.get("keep_in_sync") or [])
            continue
        if not same:
            detail = first_diff(up_text, mine_text) if up_text is not None and mine_text is not None else "（バイナリ）"
            problems.append(f"{rel}: 写し元と違います{detail}")

    for rel, allow in cfg.allowed.items():
        if rel not in used:
            problems.append(f"{rel}: 許可（kind: {allow['kind']}）に当たる差分がありません（許可を消すか path を直す）")
    return problems


def keep_in_sync(rel: str, up_text: str, mine_text: str, patterns: list[str]) -> list[str]:
    regexes = [re.compile(p) for p in patterns]
    mine_lines = {line.strip() for line in normalize(mine_text).split("\n")}
    out = []
    for line in normalize(up_text).split("\n"):
        if any(r.search(line) for r in regexes) and line.strip() not in mine_lines:
            out.append(f"{rel}: 写し元に揃える行がありません: {line.strip()}")
    return out


def first_diff(a: str, b: str) -> str:
    al, bl = normalize(a).split("\n"), normalize(b).split("\n")
    for i in range(max(len(al), len(bl))):
        x = al[i] if i < len(al) else "<なし>"
        y = bl[i] if i < len(bl) else "<なし>"
        if x != y:
            return f"\n    {i + 1} 行目  写し元: {x.strip()}\n            template: {y.strip()}"
    return ""


def fetch_upstream(repo: str, ref: str, dest: Path) -> None:
    # 手元のリポジトリ（絶対パス。Windows の C:/... を含む）はそのまま、owner/name は GitHub の URL にする
    url = repo if "://" in repo or Path(repo).is_absolute() else f"https://github.com/{repo}.git"
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", url, ref], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--template", type=Path, default=ROOT / "template", help="template ディレクトリ")
    ap.add_argument("--config", type=Path, help="既定は <template>/UPSTREAM.yaml")
    ap.add_argument("--upstream-dir", type=Path, help="写し元の checkout（指定すると取得しない）")
    ap.add_argument("--ref", help="sha の代わりに比べる ref（例: main）")
    args = ap.parse_args(argv)

    config_path = args.config or args.template / "UPSTREAM.yaml"
    try:
        cfg = load_config(config_path)
    except (OSError, ValueError) as e:
        print(f"NG: {e}")
        return 1

    tmp = None
    try:
        if args.upstream_dir:
            upstream = args.upstream_dir
            where = str(upstream)
        else:
            tmp = Path(tempfile.mkdtemp(prefix="upstream-"))
            ref = args.ref or cfg.sha
            fetch_upstream(cfg.repo, ref, tmp)
            upstream = tmp
            where = f"{cfg.repo}@{ref}"
        problems = check(args.template, upstream, cfg)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    if problems:
        print(f"NG: template と写し元（{where}）の差分のうち、UPSTREAM.yaml で説明されていないもの:")
        for p in problems:
            print(f"  - {p}")
        print("直し方: 写し元に揃える／わざと違えるなら allowed_differences に理由付きで書く")
        print("        写し元を新しくしたら UPSTREAM.yaml の sha を更新する")
        return 1
    print(f"OK: template は写し元（{where}）と一致（許可した差分 {len(cfg.allowed)} 件を除く）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
