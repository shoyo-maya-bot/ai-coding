"""scripts/check_spec_pin.py のテスト（仮のリポジトリで pin を変え、ラベルの有無で結果が変わるか）."""

import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_spec_pin as pin  # noqa: E402

A = "a" * 64
B = "b" * 64
SPEC = 'spec_id: "FEAT-X"\nsource: "docs/x.md"\nsource_sha256: "{}"\nrequirements: []\n'


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class SpecPinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        git(self.tmp, "init", "-q")
        git(self.tmp, "config", "user.email", "test@example.com")
        git(self.tmp, "config", "user.name", "test")
        git(self.tmp, "config", "core.autocrlf", "false")
        self.write("traceability/specs/x.yaml", SPEC.format(A))
        self.write("traceability/specs/y.yaml", SPEC.format(A).replace("FEAT-X", "FEAT-Y"))
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "base")
        self.base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True, capture_output=True, text=True
        ).stdout.strip()

    def tearDown(self):
        def make_writable(func, path, _exc):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        if sys.version_info >= (3, 12):
            shutil.rmtree(self.tmp, onexc=make_writable)
        else:
            shutil.rmtree(self.tmp, onerror=make_writable)

    def write(self, rel, text):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def event(self, labels):
        e = {"pull_request": {"number": 1, "base": {"sha": self.base}, "labels": [{"name": n} for n in labels]}}
        p = self.tmp / "event.json"
        p.write_text(json.dumps(e), encoding="utf-8")
        return str(p)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pin.main(["--root", str(self.tmp), *args])
        return rc, out.getvalue()

    def test_no_change_passes_without_label(self):
        self.write(
            "traceability/specs/x.yaml", SPEC.format(A).replace("requirements: []", "requirements: []\n# 説明を変えた")
        )
        rc, out = self.run_main("--event", self.event([]))
        self.assertEqual(rc, 0, out)

    def test_changed_pin_without_label_fails(self):
        self.write("traceability/specs/x.yaml", SPEC.format(B))
        rc, out = self.run_main("--event", self.event(["documentation"]))
        self.assertEqual(rc, 1, out)
        self.assertIn("traceability/specs/x.yaml: pin を変更", out)
        self.assertIn("spec-pin-approved", out)
        self.assertNotIn("y.yaml", out)

    def test_changed_pin_with_label_passes(self):
        self.write("traceability/specs/x.yaml", SPEC.format(B))
        rc, out = self.run_main("--event", self.event(["spec-pin-approved"]))
        self.assertEqual(rc, 0, out)

    def test_added_spec_with_pin_and_removed_pin_need_label(self):
        self.write("traceability/specs/z.yaml", SPEC.format(B).replace("FEAT-X", "FEAT-Z"))
        self.write("traceability/specs/y.yaml", SPEC.format(A).replace('source_sha256: "' + A + '"\n', ""))
        (self.tmp / "traceability/specs/x.yaml").unlink()
        rc, out = self.run_main("--event", self.event([]))
        self.assertEqual(rc, 1)
        self.assertIn("z.yaml: pin 付きで追加", out)
        self.assertIn("y.yaml: pin を削除", out)
        self.assertIn("x.yaml: pin 付きの対応表を削除", out)

    def test_added_spec_without_pin_passes(self):
        self.write("traceability/specs/new.yaml", 'spec_id: "FEAT-N"\nrequirements: []\n')
        rc, _ = self.run_main("--event", self.event([]))
        self.assertEqual(rc, 0)

    def test_labels_from_cli_for_local_use(self):
        self.write("traceability/specs/x.yaml", SPEC.format(B))
        self.assertEqual(self.run_main("--base", self.base, "--labels", "")[0], 1)
        self.assertEqual(self.run_main("--base", self.base, "--labels", "a, spec-pin-approved")[0], 0)

    def test_not_a_pull_request_event_is_usage_error(self):
        p = self.tmp / "push.json"
        p.write_text(json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")
        rc, out = self.run_main("--event", str(p))
        self.assertEqual(rc, 2, out)
        rc, out = self.run_main("--base", self.base, "--event", str(p))
        self.assertEqual(rc, 2, out)

    def test_broken_yaml_is_usage_error(self):
        self.write("traceability/specs/x.yaml", "source_sha256: [\n")
        rc, out = self.run_main("--event", self.event([]))
        self.assertEqual(rc, 2, out)


class WorkflowTest(unittest.TestCase):
    """決定 3 の CI: PR のイベントのラベルを読み、ラベルの付け外しでも走り直す. 権限は最小."""

    def setUp(self):
        self.wf = yaml.safe_load((ROOT / ".github/workflows/spec-pin.yml").read_text(encoding="utf-8"))

    def test_triggers_include_label_changes(self):
        on = self.wf.get("on", self.wf.get(True))
        self.assertEqual(set(on), {"pull_request"})
        self.assertTrue(
            {"opened", "synchronize", "reopened", "labeled", "unlabeled"} <= set(on["pull_request"]["types"])
        )

    def test_permissions_are_minimal(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        for job in self.wf["jobs"].values():
            self.assertNotIn("permissions", job)
            for step in job["steps"]:
                if "actions/checkout" in step.get("uses", ""):
                    self.assertFalse(step["with"]["persist-credentials"])
                self.assertNotIn("GH_TOKEN", json.dumps(step))
                self.assertNotIn("${{", step.get("run", ""))  # イベントの値を run に直接埋め込まない

    def test_runs_the_script(self):
        runs = [s.get("run", "") for j in self.wf["jobs"].values() for s in j["steps"]]
        self.assertTrue(any("scripts/check_spec_pin.py" in r for r in runs))


class RepoPinsTest(unittest.TestCase):
    def test_current_specs_are_readable(self):
        pins = pin.pins_in_tree(pin.SPECS, ROOT)
        self.assertTrue(pins)
        self.assertTrue(all(v is None or len(v) == 64 for v in pins.values()))


if __name__ == "__main__":
    unittest.main()
