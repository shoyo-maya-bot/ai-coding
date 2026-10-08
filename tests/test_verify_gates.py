"""scripts/verify-gates.sh / .ps1 と CI がずれていないかのテスト.

採点で見つかった食い違い: verify-gates は「CI と同じゲートを同じ順で」と書きながら、既定で --require を付けず、
pytest・ruff・template-drift を実行していなかった. いまは CI がこのスクリプトを呼ぶので、
ここでは sh と ps1 の中身（ゲートの順番と、各ゲートが呼ぶもの）がそろっていることと、CI が両方を呼ぶことを確かめる.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = (ROOT / "scripts/verify-gates.sh").read_text(encoding="utf-8")
PS1 = (ROOT / "scripts/verify-gates.ps1").read_text(encoding="utf-8-sig")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

# ゲート → 両方のスクリプトのそのゲートの部分に必ず含まれる文字列
EXPECTED = {
    "java": ["-p template", "--continue", "qualityGate"],
    "pytest": ["-m pytest", "tools/spec-trace/tests tests"],
    "ruff": ["ruff check tools scripts tests", "ruff format --check tools scripts tests"],
    "trace": ["spec_trace check traceability/specs", "--enforce-drift", "--require", "--test-results"],
    "authority": ["scripts/verify_authority.py"],
    "docs": ["scripts/check_docs.py"],
    "drift": ["scripts/check_template_drift.py"],
}


def gates(text: str) -> dict[str, str]:
    """「# gate: 名前」から次の「# gate:」までを、そのゲートの部分として返す."""
    parts = re.split(r"(?m)^# gate: (\w+)\s*$", text)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


class VerifyGatesTest(unittest.TestCase):
    def test_same_gates_in_same_order(self):
        self.assertEqual(list(gates(SH)), list(EXPECTED))
        self.assertEqual(list(gates(PS1)), list(EXPECTED))

    def test_each_gate_runs_the_same_things(self):
        for name, script in (("sh", SH), ("ps1", PS1)):
            parts = gates(script)
            for gate, needles in EXPECTED.items():
                for needle in needles:
                    with self.subTest(script=name, gate=gate, needle=needle):
                        self.assertIn(needle, parts[gate])

    def test_default_requires_implemented_and_final_requires_proven(self):
        self.assertIn('REQUIRE="implemented"', SH)
        self.assertIn('--final) REQUIRE="proven"', SH)
        self.assertIn("$require = if ($Final) { 'proven' } else { 'implemented' }", PS1)

    def test_no_ampersands_in_powershell_script(self):
        # Windows PowerShell 5.1 は && を解釈できない
        self.assertNotIn("&&", PS1)

    def test_ci_calls_both_scripts(self):
        self.assertIn("./scripts/verify-gates.sh", CI)
        self.assertIn(".\\scripts\\verify-gates.ps1", CI)
        self.assertIn("windows-latest", CI)


if __name__ == "__main__":
    unittest.main()
