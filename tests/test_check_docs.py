"""scripts/check_docs.py のテスト（小さな仮リポジトリを作って壊し、検知できるか）."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_docs  # noqa: E402

SUMMARY = "禁止: 期待値を実装に合わせる、アサーションを消す・弱める"
PROHIBITION_SOURCE = (
    "# 進め方\n\n## 禁止事項（ゲートのこじ開け）\n\n- 期待値を実装に合わせる\n- アサーションを消す・弱める\n\n"
    f"<!-- prohibitions:begin -->\n{SUMMARY}\n<!-- prohibitions:end -->\n\n## 次の節\n\n- 関係ない項目\n"
)


class CheckDocsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.write(
            "README.md",
            "# 概要\n\n[手順](docs/guide.md#2-使い方) と [設定](config.yaml)、[外部](https://example.com)\n",
        )
        self.write("docs/guide.md", "# ガイド\n\n## 2. 使い方\n\n## 2. 使い方\n\n[上へ](#ガイド) [重複](#2-使い方-1)\n")
        self.write("config.yaml", "a: 1\n")
        self.write("data.json", '{"a": 1}\n')
        self.write("samples/docs/x.md", "# x\n")
        self.write("tpl/batch.md", "# t\n")
        self.write(
            "context-sources.yaml",
            "roots:\n  - path: samples/docs\n  # - path: ../outside\ntypes:\n  batch: { template: tpl/batch.md }\n",
        )
        self.write(".github/instructions/java.instructions.md", '---\napplyTo: "**/*.java"\n---\n\n- rule\n')
        self.write(".github/prompts/run.prompt.md", "---\ndescription: 実行する\n---\n\n本文\n")
        self.write(".github/skills/demo/SKILL.md", "---\nname: demo\ndescription: デモ\n---\n\n# demo\n")
        # 禁止事項の正と複写先（7 ファイル）
        self.write("guidelines/workflow.md", PROHIBITION_SOURCE)
        for rel in check_docs.PROHIBITIONS_COPIES:
            self.write(rel, f"---\ndescription: x\n---\n\n- 前の行\n- {SUMMARY}\n- 後の行\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel, text):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def errors(self):
        return check_docs.verify(self.tmp)

    def assertError(self, *words):
        errs = self.errors()
        self.assertTrue(any(all(w in e for w in words) for e in errs), errs)

    def test_valid_tree_has_no_errors(self):
        self.assertEqual(self.errors(), [])

    def test_repository_is_consistent(self):
        self.assertEqual(check_docs.verify(ROOT), [])

    def test_agent_command_with_ampersands_is_reported(self):
        # 起きうる書き方: Windows PowerShell 5.1 は && を解釈できず、エージェントの自動修正ループが最初で止まる
        self.write(
            ".github/agents/coder.agent.md",
            "---\ndescription: x\n---\n\n1. `cd template && ./gradlew test` を実行する\n"
            f"2. `&&` は使えない（説明は可）\n\n- {SUMMARY}\n",
        )
        errs = self.errors()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("coder.agent.md:5", errs[0])
        self.assertIn("&&", errs[0])

    def test_command_with_ampersands_in_code_block_of_prompt_is_reported(self):
        self.write(".github/prompts/run.prompt.md", "---\ndescription: x\n---\n\n```\ncd a && b\n```\n")
        self.assertError("run.prompt.md:6", "&&")

    def test_ampersands_outside_copilot_files_are_allowed(self):
        self.write("docs/bash.md", "# bash\n\n```bash\ncd a && b\n```\n")
        self.assertEqual(self.errors(), [])

    # --- 第 2 回の指摘: 禁止事項の 7 ファイルへの複写の一致 ---

    def test_prohibitions_copy_differs(self):
        # 1 ファイルだけ書き換える（項目を落とす）と、そのファイルを指して失敗する
        rel = ".github/agents/tester.agent.md"
        self.write(rel, "---\ndescription: x\n---\n\n- 禁止: 期待値を実装に合わせる\n")
        errs = self.errors()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn(rel, errs[0])
        self.assertIn("一致しません", errs[0])

    def test_prohibitions_copy_missing_line_or_file(self):
        self.write(".github/agents/coder.agent.md", "---\ndescription: x\n---\n\n- 何もない\n")
        self.assertError("coder.agent.md", "「- 禁止: 」の行がありません")
        (self.tmp / ".github/agents/planner.agent.md").unlink()
        self.assertError("planner.agent.md", "ありません")

    def test_prohibitions_list_and_summary_count(self):
        # 正の一覧に項目を足して、要約を直し忘れた
        self.write(
            "guidelines/workflow.md", PROHIBITION_SOURCE.replace("- アサーション", "- 閾値を下げる\n- アサーション")
        )
        self.assertError("guidelines/workflow.md", "3 項目", "2 項目")

    def test_prohibitions_summary_block_required(self):
        self.write("guidelines/workflow.md", "# 進め方\n\n## 禁止事項\n\n- a\n")
        self.assertError("guidelines/workflow.md", "prohibitions:begin")

    def test_prohibitions_whitespace_and_width_are_normalized(self):
        # 全角・半角や行頭の空白の違いは同じとみなす（NFKC）
        rel = ".github/agents/reviewer.agent.md"
        self.write(rel, f"---\ndescription: x\n---\n\n-   {SUMMARY.replace(':', '：')}\n")
        self.assertEqual(self.errors(), [])

    def test_pre_push_hook_runs_check_docs(self):
        hook = (ROOT / ".githooks/pre-push").read_text(encoding="utf-8")
        self.assertTrue(hook.startswith("#!/usr/bin/env sh"))
        self.assertIn("scripts/check_docs.py", hook)
        self.assertIn("exit 1", hook)
        self.assertIn("git config core.hooksPath .githooks", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_missing_link_target(self):
        self.write("README.md", "[なし](docs/none.md)\n")
        self.assertError("README.md:1", "リンク先がない", "docs/none.md")

    def test_missing_anchor(self):
        self.write("README.md", "[なし](docs/guide.md#存在しない)\n")
        self.assertError("見出しアンカーがない", "#存在しない")

    def test_same_file_anchor_and_html_anchor(self):
        self.write("README.md", '# 表題\n\n<a id="here"></a>\n\n[a](#表題) [b](#here) [c](#nothere)\n')
        errs = self.errors()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("#nothere", errs[0])

    def test_links_in_code_are_ignored(self):
        self.write("README.md", "`[x](none.md)`\n\n```md\n[y](none.md)\n```\n")
        self.assertEqual(self.errors(), [])

    def test_link_outside_repository(self):
        self.write("README.md", "[外](../../etc/passwd)\n")
        self.assertError("リポジトリの外")

    def test_reference_definition(self):
        self.write("README.md", "[参照][r]\n\n[r]: docs/missing.md\n")
        self.assertError("リンク先がない", "docs/missing.md")

    def test_slugify_matches_github(self):
        self.assertEqual(check_docs.slugify("2. 使い方 (Usage)!"), "2-使い方-usage")
        self.assertEqual(check_docs.slugify("`code` と [link](x.md)"), "code-と-link")

    def test_context_sources_missing_root_and_template(self):
        self.write(
            "context-sources.yaml",
            "roots:\n  - path: samples/none\ntypes:\n  api: { template: tpl/none.md }\n",
        )
        self.assertError("roots[0].path", "samples/none")
        self.assertError("types.api.template", "tpl/none.md")

    def test_broken_yaml_and_json(self):
        self.write("bad.yml", "a: [1, 2\n")
        self.write("bad.json", "{a: 1}\n")
        self.assertError("bad.yml", "YAML")
        self.assertError("bad.json", "JSON")

    def test_multi_document_yaml_is_allowed(self):
        self.write("multi.yml", "a: 1\n---\nb: 2\n")
        self.assertEqual(self.errors(), [])

    def test_instructions_without_apply_to(self):
        self.write(".github/instructions/java.instructions.md", "---\ndescription: x\n---\n")
        self.assertError("java.instructions.md", "applyTo")

    def test_prompt_without_front_matter(self):
        self.write(".github/prompts/run.prompt.md", "本文だけ\n")
        self.assertError("run.prompt.md", "Front Matter")

    def test_broken_front_matter(self):
        self.write(".github/prompts/run.prompt.md", "---\ndescription: [x\n---\n")
        self.assertError("run.prompt.md", "YAML")

    def test_skill_name_must_match_folder(self):
        self.write(".github/skills/demo/SKILL.md", "---\nname: other\ndescription: d\n---\n")
        self.assertError("SKILL.md", "フォルダ名")


if __name__ == "__main__":
    unittest.main()
