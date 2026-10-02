"""scripts/verify_authority.py のテスト（実リポジトリを複製して壊し、検知できるか）."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_authority  # noqa: E402


class AuthorityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for d in ["traceability", "guidelines", "scripts", ".github/agents"]:
            shutil.copytree(ROOT / d, self.tmp / d)
        (self.tmp / "template").mkdir()
        shutil.copy(ROOT / "template/build.gradle", self.tmp / "template/build.gradle")
        (self.tmp / "tools/spec-trace").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, rel, old, new):
        p = self.tmp / rel
        s = p.read_text(encoding="utf-8")
        self.assertIn(old, s)
        p.write_text(s.replace(old, new, 1), encoding="utf-8")

    def test_repository_is_consistent(self):
        self.assertEqual(verify_authority.verify(ROOT), [])

    def test_check_without_rule(self):
        self.edit("traceability/authority.yaml", "rules: [R-COMPILE]", "rules: [R-UNKNOWN]")
        errs = verify_authority.verify(self.tmp)
        self.assertTrue(any("越権" in e for e in errs))
        self.assertTrue(any("R-COMPILE" in e and "空文化" in e for e in errs))

    def test_missing_heading(self):
        self.edit("traceability/authority.yaml", "coding-standards.md#命名", "coding-standards.md#存在しない見出し")
        self.assertTrue(any("見出しがありません" in e for e in verify_authority.verify(self.tmp)))

    def test_missing_gradle_task(self):
        self.edit("template/build.gradle", "tasks.register('verifyMapperSql')", "tasks.register('renamedTask')")
        self.assertTrue(any("verifyMapperSql" in e for e in verify_authority.verify(self.tmp)))


if __name__ == "__main__":
    unittest.main()
