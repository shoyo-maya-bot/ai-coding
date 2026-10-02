"""spec-trace のテスト.

samples/project（全要件が裏付け済みのサンプル）を一時ディレクトリに複製し、
定義やコードを壊したときに正しく検知できるかを確かめる。
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import jsonschema
from devtools_common.cli import run_main
from devtools_common.report import report_schema

from spec_trace import cli
from spec_trace.code import lookup_scenario, lookup_symbol, split_symbol
from spec_trace.core import sha256_of

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "project"
SPEC = "traceability/order-import.yaml"


def run_cli(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = run_main(cli.main, list(args))
    return rc, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.proj = self.tmp / "project"
        shutil.copytree(SAMPLE, self.proj)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.proj / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def check(self, *extra: str) -> tuple[int, dict]:
        rc, out, _ = run_cli("check", str(self.proj / "traceability"), "--root", str(self.proj), "-f", "json", *extra)
        return rc, json.loads(out)

    def rules(self, data: dict) -> list[str]:
        return [f["rule_id"] for f in data["findings"] if f["severity"] != "info"]


class SampleTest(Base):
    def test_sample_is_clean_and_report_follows_spec(self):
        rc, data = self.check("--require", "proven", "--enforce-drift")
        self.assertEqual((rc, self.rules(data)), (0, []))
        jsonschema.validate(data, report_schema())
        self.assertEqual(data["meta"]["proven"], 3)
        self.assertEqual(data["meta"]["proven_ratio"], "100%")


class ImplementsTest(Base):
    def test_missing_symbol(self):
        self.edit("src/order_import.py", "def import_orders(", "def import_orders_v2(")
        rc, data = self.check()
        self.assertEqual(rc, 1)
        self.assertEqual(self.rules(data), ["trace.implements_missing"])
        self.assertIn("REQ-ORDER-002", data["findings"][0]["location"])

    def test_missing_file(self):
        (self.proj / "java/main/OrderImportJob.java").unlink()
        rc, data = self.check()
        self.assertEqual(rc, 1)
        self.assertEqual(set(self.rules(data)), {"trace.implements_missing"})

    def test_implemented_without_implements(self):
        self.edit(
            SPEC,
            '    implements:\n      - file: "src/order_import.py"\n        symbol: "OrderValidator#validate"\n',
            "",
        )
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.implements_empty"])

    def test_method_in_wrong_class_is_not_found(self):
        self.edit(SPEC, "OrderValidator#validate", "OtherClass#validate")
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.implements_missing"])


class ProofsTest(Base):
    def test_test_without_assertion(self):
        self.edit("tests/test_order_import.py", "        assert OrderValidator()", "        OrderValidator()")
        rc, data = self.check()
        self.assertEqual(rc, 1)
        self.assertEqual(self.rules(data), ["trace.proof_no_assert"])

    def test_java_test_without_assertion(self):
        p = self.proj / "java/test/OrderImportJobTest.java"
        p.write_text(p.read_text(encoding="utf-8").replace("assertThat(", "System.out.println("), encoding="utf-8")
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.proof_no_assert"])

    def test_ignored_scenario(self):
        self.edit("e2e/order-import.feature", "  Scenario:", "  @ignore\n  Scenario:")
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.proof_ignored"])

    def test_scenario_without_then(self):
        self.edit("e2e/order-import.feature", "    Then 結果ファイルの取込件数は 3\n    And エラー件数は 0\n", "")
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.proof_no_assert"])

    def test_proven_without_proofs(self):
        self.edit(
            SPEC,
            '    proofs:\n      - file: "e2e/order-import.feature"\n        scenario: "結果ファイルに件数が出る"\n'
            '        type: "normal"\n',
            "",
        )
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.proofs_empty"])

    def test_pending_is_info_unless_required(self):
        self.edit(SPEC, 'status: "proven"', 'status: "pending"')
        rc, data = self.check()
        self.assertEqual((rc, self.rules(data)), (0, []))
        self.assertIn("trace.pending", [f["rule_id"] for f in data["findings"]])
        rc, data = self.check("--require", "implemented")
        self.assertEqual((rc, self.rules(data)), (1, ["trace.not_done"]))


class DriftTest(Base):
    def test_changed_design_doc_is_drift(self):
        self.edit("docs/design/order-import.md", "数量は 1 以上。", "数量は 1 以上 999 以下。")
        rc, data = self.check()
        self.assertEqual((rc, self.rules(data)), (1, ["trace.spec_drift"]))
        # レビュー後に pin し直すと解消する
        rc, out, _ = run_cli("pin", str(self.proj / SPEC), "--root", str(self.proj))
        self.assertEqual(rc, 0)
        self.assertEqual(self.check()[0], 0)

    def test_crlf_checkout_is_not_drift(self):
        p = self.proj / "docs/design/order-import.md"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.check()[0], 0)

    def test_missing_design_doc_is_warning_unless_enforced(self):
        shutil.rmtree(self.proj / "docs")
        rc, data = self.check()
        self.assertEqual((rc, self.rules(data)), (0, ["trace.source_missing"]))
        self.assertEqual(self.check("--enforce-drift")[0], 1)

    def test_pin_inserts_hash_after_source(self):
        self.edit(SPEC, 'source_sha256: "', 'x_removed: "')
        p = self.proj / SPEC
        p.write_text("\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines() if "x_removed" not in ln) + "\n")
        _, data = self.check()
        self.assertEqual(self.rules(data), ["trace.source_unpinned"])
        run_cli("pin", str(p), "--root", str(self.proj))
        lines = p.read_text(encoding="utf-8").splitlines()
        i = lines.index('source: "docs/design/order-import.md"')
        self.assertEqual(lines[i + 1], f'source_sha256: "{sha256_of(self.proj / "docs/design/order-import.md")}"')


class SpecFileTest(Base):
    def test_schema_error_is_usage_error(self):
        self.edit(SPEC, 'status: "proven"', 'status: "done"')
        rc, _, err = run_cli("check", str(self.proj / "traceability"), "--root", str(self.proj))
        self.assertEqual(rc, 2)
        self.assertIn("形式が不正", err)

    def test_duplicate_id_across_files(self):
        shutil.copy(self.proj / SPEC, self.proj / "traceability/copy.yaml")
        _, data = self.check()
        self.assertEqual(set(self.rules(data)), {"trace.duplicate_id"})

    def test_schema_command(self):
        rc, out, _ = run_cli("schema")
        self.assertEqual(rc, 0)
        self.assertIn("requirements", json.loads(out)["properties"])


class CodeLookupTest(unittest.TestCase):
    def write(self, name: str, text: str) -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        p = d / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_split_symbol(self):
        self.assertEqual(split_symbol("A#b"), ("A", "b"))
        self.assertEqual(split_symbol("pkg.mod.A.b"), ("A", "b"))
        self.assertEqual(split_symbol("TestX::test_y"), ("TestX", "test_y"))
        self.assertEqual(split_symbol("f"), (None, "f"))

    def test_java_call_is_not_a_declaration(self):
        p = self.write("A.java", "class A {\n  void run() {\n    process(x);\n  }\n}\n")
        self.assertFalse(lookup_symbol(p, "A#process").found)
        self.assertTrue(lookup_symbol(p, "A#run").found)

    def test_comment_mention_is_not_a_declaration(self):
        p = self.write("A.java", "class A {\n  // void hidden() {\n}\n")
        self.assertFalse(lookup_symbol(p, "A#hidden").found)

    def test_kotlin_and_typescript(self):
        kt = self.write("T.kt", "class T {\n  @Test\n  fun works() {\n    assertEquals(1, 1)\n  }\n}\n")
        self.assertEqual(lookup_symbol(kt, "T#works").asserts, 1)
        ts = self.write("a.test.ts", "describe('x', () => {});\nfunction helper() {\n  expect(1).toBe(1);\n}\n")
        self.assertEqual(lookup_symbol(ts, "helper").asserts, 2)

    def test_mockmvc_and_expect_counts(self):
        body = '    mvc.perform(get("/")).andExpect(status().isOk());\n'
        p = self.write("C.java", "class C {\n  void t() throws Exception {\n" + body + "  }\n}\n")
        self.assertEqual(lookup_symbol(p, "C#t").asserts, 1)

    def test_python_mock_assertions_count(self):
        p = self.write("t.py", "def test_x(m):\n    m.run()\n    m.run.assert_called_once()\n")
        self.assertEqual(lookup_symbol(p, "test_x").asserts, 1)

    def test_japanese_gherkin(self):
        p = self.write("a.feature", "機能: x\n\n  シナリオ: 正常\n    前提 a\n    もし b\n    ならば c\n")
        self.assertEqual(lookup_scenario(p, "正常").checks, 1)


if __name__ == "__main__":
    unittest.main()
