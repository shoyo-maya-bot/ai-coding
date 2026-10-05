"""scripts/check_docs.py のテスト（小さな仮リポジトリを作って壊し、検知できるか）."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_docs  # noqa: E402


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
