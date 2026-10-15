"""scripts/verify_authority.py のテスト（実リポジトリを複製して壊し、検知できるか）."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_authority  # noqa: E402


class RepoCopy(unittest.TestCase):
    """実リポジトリの必要な部分を一時ディレクトリに複製する."""

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


class AuthorityTest(RepoCopy):
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


class GateStrengthTest(RepoCopy):
    """D11: build.gradle でゲートが弱められていないか（チェックは実在しても効いていない状態）を検出する."""

    def errors(self) -> list[str]:
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("ORG_GRADLE_PROJECT_branchCoverageMinimum", "GRADLE_OPTS", "JAVA_OPTS", "JAVA_TOOL_OPTIONS"):
                os.environ.pop(k, None)
            return verify_authority.verify(self.tmp)

    def assert_weakened(self, *words: str) -> None:
        errs = self.errors()
        self.assertTrue(any(all(w in e for w in words) for e in errs), errs)

    def test_copy_is_clean(self):
        self.assertEqual(self.errors(), [])

    def test_spotbugs_removed_from_quality_gate(self):
        self.edit(
            "template/build.gradle",
            "\n            'spotbugsMain', 'verifyMapperSql'",
            "\n            'verifyMapperSql'",
        )
        self.assert_weakened("qualityGate", "spotbugsMain")

    def test_coverage_verification_removed_from_quality_gate(self):
        self.edit("template/build.gradle", "'test', 'jacocoTestCoverageVerification',", "'test',")
        self.assert_weakened("qualityGate", "jacocoTestCoverageVerification")

    def test_ignore_failures_true(self):
        self.edit(
            "template/build.gradle", "spotbugs {\n    ignoreFailures = false", "spotbugs {\n    ignoreFailures = true"
        )
        self.assert_weakened("ignoreFailures = true")

    def test_ignore_failures_in_comment_is_not_counted(self):
        self.edit("template/build.gradle", "spotbugs {\n", "spotbugs {\n    // ignoreFailures = true にしない\n")
        self.assertEqual(self.errors(), [])

    def test_checkstyle_max_warnings_raised(self):
        self.edit("template/build.gradle", "maxWarnings = 0", "maxWarnings = 10")
        self.assert_weakened("maxWarnings = 10")

    def test_gate_task_disabled(self):
        self.edit(
            "template/build.gradle",
            "tasks.named('spotbugsTest') { enabled = false }",
            "tasks.named('spotbugsMain') { enabled = false }",
        )
        self.assert_weakened("spotbugsMain", "enabled = false")

    def test_fail_on_violation_false(self):
        self.edit(
            "template/build.gradle", "    violationRules {\n", "    violationRules {\n        failOnViolation = false\n"
        )
        self.assert_weakened("failOnViolation = false")

    def test_branch_coverage_floor_lowered(self):
        self.edit("template/build.gradle", "new BigDecimal('0.80')", "new BigDecimal('0.50')")
        self.assert_weakened("branchCoverageFloor", "0.50")

    def test_branch_coverage_floor_raised_is_fine(self):
        self.edit("template/build.gradle", "new BigDecimal('0.80')", "new BigDecimal('0.90')")
        self.assertEqual(self.errors(), [])

    def test_old_style_default_without_floor_guard(self):
        self.edit("template/build.gradle", "if (branchMinimum < branchCoverageFloor) {", "if (false) {")
        self.assert_weakened("D4", "if (branchMinimum < branchCoverageFloor)")

    def test_property_lowered_in_verify_gates(self):
        self.edit(
            "scripts/verify-gates.sh", "--continue qualityGate", "--continue qualityGate -PbranchCoverageMinimum=0.5"
        )
        self.assert_weakened("verify-gates.sh", "0.5")

    def test_property_raised_in_verify_gates_is_fine(self):
        self.edit(
            "scripts/verify-gates.sh", "--continue qualityGate", "--continue qualityGate -PbranchCoverageMinimum=1.0"
        )
        self.assertEqual(self.errors(), [])

    def test_property_lowered_in_gradle_properties(self):
        (self.tmp / "template/gradle.properties").write_text("branchCoverageMinimum=0.3\n", encoding="utf-8")
        self.assert_weakened("gradle.properties", "0.3")

    def test_property_lowered_in_workflow_env(self):
        wf = self.tmp / ".github/workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text('env:\n  ORG_GRADLE_PROJECT_branchCoverageMinimum: "0.1"\n', encoding="utf-8")
        self.assert_weakened("ci.yml", "0.1")

    def test_property_lowered_in_environment_of_this_run(self):
        with mock.patch.dict(os.environ, {"ORG_GRADLE_PROJECT_branchCoverageMinimum": "0.2"}):
            errs = verify_authority.verify(self.tmp)
        self.assertTrue(any("ORG_GRADLE_PROJECT_branchCoverageMinimum=0.2" in e for e in errs), errs)
        with mock.patch.dict(os.environ, {"GRADLE_OPTS": "-Dorg.gradle.project.branchCoverageMinimum=0.2"}):
            errs = verify_authority.verify(self.tmp)
        self.assertTrue(any("GRADLE_OPTS" in e for e in errs), errs)

    def test_repository_workflows_do_not_lower_coverage(self):
        self.assertEqual(verify_authority.check_coverage_overrides(ROOT, verify_authority.MIN_BRANCH_COVERAGE), [])


if __name__ == "__main__":
    unittest.main()
