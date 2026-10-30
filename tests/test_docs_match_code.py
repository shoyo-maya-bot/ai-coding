"""ドキュメントと実際の動き（オプション・終了コード・対応 Python・ゲートの中身）のずれを機械で見つける."""

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_authority  # noqa: E402
from spec_trace import cli as spec_trace_cli  # noqa: E402
from test_scaffold import cli as scaffold_cli  # noqa: E402
from test_scaffold.errors import ExitCode as ScaffoldExit  # noqa: E402


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    m = re.search(rf"^##+ {re.escape(heading)}\s*$(.*?)(?=^##+ |\Z)", text, re.M | re.S)
    if m is None:
        raise AssertionError(f"見出し「{heading}」がありません")
    return m.group(1)


def table_first_cells(text: str) -> list[str]:
    cells = []
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            cells.append(line.split("|")[1].strip())
    return cells[1:]  # 見出し行を除く


def exit_codes_in_help(text: str) -> dict[int, str]:
    """「終了コード: 0 成功 / 1 … / 2 …」の行 → {コード: 意味}."""
    m = re.search(r"終了コード:\s*(.+)", text)
    if m is None:
        raise AssertionError("終了コードの行がありません")
    return {int(k): v.strip() for k, v in re.findall(r"(\d+)\s+([^/]+)", m.group(1))}


class PythonVersionTest(unittest.TestCase):
    def test_readme_and_scripts_state_requires_python(self):
        versions = set()
        for tool in ("spec-trace", "test-scaffold"):
            # tomllib は 3.11 から（requires-python の下限 3.10 でも動くように行で読む）
            m = re.search(r'^requires-python\s*=\s*">=\s*(3\.\d+)"', read(f"tools/{tool}/pyproject.toml"), re.M)
            self.assertIsNotNone(m, tool)
            versions.add(m.group(1))
        self.assertEqual(len(versions), 1, "ツールごとに requires-python が違う")
        (minimum,) = versions
        self.assertIn(f"Python {minimum} 以上", read("README.md"))
        for rel in ("scripts/verify-gates.sh", "scripts/verify-gates.ps1"):
            self.assertIn(f"Python {minimum} 以上", read(rel), rel)
        # constraints.txt を作る Python の版も同じ下限
        self.assertIn(f"--python-version {minimum}", read(".github/workflows/deps-lock.yml"))
        self.assertEqual(read("ruff.toml").count(f'target-version = "py{minimum.replace(".", "")}"'), 1)


class TestScaffoldDocsTest(unittest.TestCase):
    readme = read("tools/test-scaffold/README.md")

    def test_options_table_matches_parser(self):
        parser = scaffold_cli.build_parser()
        flags = {s for a in parser._actions for s in a.option_strings if s.startswith("--") and s != "--help"}  # noqa: SLF001
        documented = set()
        for cell in table_first_cells(section(self.readme, "オプション")):
            documented |= set(re.findall(r"`(--[a-z-]+)", cell))
        self.assertEqual(documented, flags)

    def test_exit_codes_match_enum_and_help(self):
        table = {int(c) for c in table_first_cells(section(self.readme, "終了コード"))}
        self.assertEqual(table, {int(c) for c in ScaffoldExit})
        self.assertEqual(set(exit_codes_in_help(scaffold_cli.__doc__)), table)

    def test_default_out_matches_parser(self):
        parser = scaffold_cli.build_parser()
        default = parser.get_default("out").as_posix()
        self.assertIn(f"既定: `{default}`", self.readme)


class SpecTraceDocsTest(unittest.TestCase):
    def test_exit_codes_match_help(self):
        readme = read("tools/spec-trace/README.md")
        table = {int(c) for c in table_first_cells(section(readme, "終了コード"))}
        self.assertEqual(table, set(exit_codes_in_help(spec_trace_cli.__doc__)))

    def test_check_options_in_readme_exist(self):
        parser = spec_trace_cli.build_parser()
        sub = next(a for a in parser._actions if a.dest == "command")  # noqa: SLF001
        flags = {s for a in sub.choices["check"]._actions for s in a.option_strings}  # noqa: SLF001
        readme = read("tools/spec-trace/README.md")
        other = {"--final", "--junitxml"}  # verify-gates・pytest のオプション
        for flag in set(re.findall(r"`(--[a-z-]+)", readme)) - other:
            self.assertIn(flag, flags, f"README の {flag} が spec-trace check にありません")


class GateDocsTest(unittest.TestCase):
    def test_quality_gates_pytest_row_matches_verify_gates(self):
        sh = read("scripts/verify-gates.sh")
        m = re.search(r"-m pytest -q ([^\n]+)", sh)
        self.assertIsNotNone(m)
        paths = m.group(1).split()
        row = next(ln for ln in read("guidelines/quality-gates.md").splitlines() if "ツールのテスト" in ln)
        self.assertIn("pytest " + " ".join(paths), row)

    def test_verify_authority_files_are_documented(self):
        gates = read("guidelines/quality-gates.md")
        for word in (verify_authority.BASELINE, "--write-baseline", "checkstyle.xml", "exclude.xml"):
            self.assertIn(word, gates)
        self.assertIn(verify_authority.BASELINE, read("README.md"))

    def test_branch_coverage_floor_in_docs_matches_script(self):
        pct = f"{int(verify_authority.MIN_BRANCH_COVERAGE * 100)}%"
        self.assertIn(f"下限 {pct}", read("guidelines/quality-gates.md"))
        self.assertIn(f"下限 {pct}", read("README.md"))
        build = read("template/build.gradle")
        self.assertIn(f"new BigDecimal('{verify_authority.MIN_BRANCH_COVERAGE}')", build)


class RepoSettingsDocsTest(unittest.TestCase):
    """第 8 回の指摘: README の権限・Dependabot・実案件の手順が実際の設定とずれていた."""

    readme = read("README.md")

    def test_workflow_permissions_match_readme(self):
        documented = set()
        for line in section(self.readme, "変更点").splitlines():
            m = re.match(r"^\|\s*([\w-]+)（([\w-]+)）\s*\|\s*`([\w-]+): (\w+)`", line)
            if m:
                documented.add(m.groups())
        actual = set()
        for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
            data = yaml.safe_load(wf.read_text(encoding="utf-8"))
            self.assertEqual(data.get("permissions"), {"contents": "read"}, f"{wf.name} の既定の権限")
            for job_id, job in data["jobs"].items():
                for perm, level in (job.get("permissions") or {}).items():
                    if level != "read":
                        actual.add((wf.stem, job_id, perm, level))
        self.assertEqual(documented, actual)

    def test_dependabot_covers_every_python_tool(self):
        data = yaml.safe_load(read(".github/dependabot.yml"))
        pip_dirs = {u["directory"] for u in data["updates"] if u["package-ecosystem"] == "pip"}
        tools = {f"/{p.parent.relative_to(ROOT).as_posix()}" for p in (ROOT / "tools").glob("*/pyproject.toml")}
        self.assertEqual(pip_dirs, tools)

    def test_ci_runs_the_minimum_python(self):
        m = re.search(r'^requires-python\s*=\s*">=\s*(3\.\d+)"', read("tools/spec-trace/pyproject.toml"), re.M)
        self.assertIn(f'python-version: "{m.group(1)}"', read(".github/workflows/ci.yml"))
        self.assertIn(f"下限の {m.group(1)} でも実行", self.readme)

    def test_real_project_steps_name_what_hardcodes_the_package(self):
        steps = section(self.readme, "実案件で使う")
        upstream = yaml.safe_load(read("template/UPSTREAM.yaml"))
        for r in upstream["rename"]:
            if r["to"].startswith("com"):
                self.assertIn(f"`{r['to']}`", steps)
        self.assertIn("REQUIRED_COVERAGE_TARGETS", steps)
        self.assertIn(verify_authority.REQUIRED_COVERAGE_TARGETS[0], steps)
        self.assertIn(f"`{upstream['repo']}`", steps)
        self.assertIn("--upstream-dir", steps)


if __name__ == "__main__":
    unittest.main()
