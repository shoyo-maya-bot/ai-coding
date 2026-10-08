"""eval の運用手順と記録の例、AI 利用の上限がドキュメントに書かれていることを確かめる."""

import csv
import io
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class EvalDocsTest(unittest.TestCase):
    def test_example_row_matches_metrics_header(self):
        # 例の 1 行が metrics.csv の見出しと同じ列数・同じ形で書かれている（そのまま写して使える）
        header = next(csv.reader(io.StringIO(read("eval/metrics.csv"))))
        m = re.search(r"```csv\n(.+?)\n```", read("eval/README.md"))
        self.assertIsNotNone(m, "eval/README.md に metrics.csv の例の行が無い")
        row = next(csv.reader(io.StringIO(m.group(1))))
        self.assertEqual(len(row), len(header))
        rec = dict(zip(header, row, strict=True))
        self.assertRegex(rec["run_id"], r"^run-\d{8}-[A-Z0-9]+-(gen|human)-\d{2}$")
        self.assertTrue(0 <= float(rec["branch_coverage"]) <= 1)
        self.assertIn(rec["escalated"], {"0", "1"})

    def test_example_is_marked_fictional_and_not_in_metrics(self):
        text = read("eval/README.md")
        self.assertIn("最初の記録の例（架空）", text)
        self.assertIn("運用の流れ", text)
        self.assertEqual(len(read("eval/metrics.csv").strip().splitlines()), 1)  # 実際のランの値だけを入れる

    def test_workflow_points_to_eval_procedure(self):
        self.assertIn("eval/metrics.csv", read("WORKFLOW.md"))


class UsageLimitDocsTest(unittest.TestCase):
    def test_guidelines_define_cost_and_request_limits(self):
        text = read("guidelines/ai-principles.md")
        self.assertIn("## AI 利用の上限", text)
        self.assertIn("既定 0 円", text)
        self.assertRegex(text, r"プレミアムリクエスト \| \d+ 回")

    def test_run_record_has_request_count(self):
        self.assertIn("AI のリクエスト数", read("eval/templates/run-record.md"))


if __name__ == "__main__":
    unittest.main()
