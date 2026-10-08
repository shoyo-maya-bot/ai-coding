"""scripts/check_template_drift.py のテスト（仮の写し元と template を作ってずらし、検知できるか）."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_template_drift as drift  # noqa: E402

CONFIG = """\
repo: example/upstream
sha: 0123456789abcdef0123456789abcdef01234567
mappings:
  - {upstream: sample-app, template: .}
  - {upstream: local, template: local}
rename:
  - {from: com.example.sample, to: com.example.app}
  - {from: com/example/sample, to: com/example/app}
ignore: [build/]
allowed_differences:
  - path: settings.gradle
    kind: replace
    replace: [{from: "'sample-app'", to: "'app'"}]
    reason: 汎用名にする
  - path: build.gradle
    kind: modified
    keep_in_sync: ["^\\\\s*implementation "]
    reason: ゲートを足す
  - path: UPSTREAM.yaml
    kind: added
    reason: この設定
  - path: local/README.md
    kind: removed
    reason: 持ち込まない
"""


class TemplateDriftTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.up = self.tmp / "upstream"
        self.tpl = self.tmp / "template"
        self.write(self.up, "sample-app/settings.gradle", "rootProject.name = 'sample-app'\n")
        self.write(self.up, "sample-app/build.gradle", "dependencies {\n    implementation 'a:b:1.0'\n}\n")
        self.write(
            self.up,
            "sample-app/src/main/java/com/example/sample/A.java",
            "package com.example.sample;\n\nclass A {}\n",
        )
        self.write(self.up, "sample-app/build/out.txt", "成果物\n")
        self.write(self.up, "local/README.md", "# 手順\n")
        self.write(self.up, "local/compose.yml", "name: dev\n")
        self.write(self.tpl, "settings.gradle", "rootProject.name = 'app'\n")
        gradle = "plugins { id 'checkstyle' }\ndependencies {\n  implementation 'a:b:1.0'\n}\n"
        self.write(self.tpl, "build.gradle", gradle)
        self.write(self.tpl, "src/main/java/com/example/app/A.java", "package com.example.app;\n\nclass A {}\n")
        self.write(self.tpl, "local/compose.yml", "name: dev\n")
        self.write(self.tpl, "build/other.txt", "無視される\n")
        self.write(self.tpl, "UPSTREAM.yaml", CONFIG)

    def tearDown(self):
        # Windows では git のオブジェクトが読み取り専用で、そのままでは消せない. 書き込み可にしてから消す
        def make_writable(func, path, _exc):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        if sys.version_info >= (3, 12):
            shutil.rmtree(self.tmp, onexc=make_writable)
        else:
            shutil.rmtree(self.tmp, onerror=make_writable)

    def write(self, base, rel, text):
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def problems(self):
        cfg = drift.load_config(self.tpl / "UPSTREAM.yaml")
        return drift.check(self.tpl, self.up, cfg)

    def assert_problem(self, needle):
        problems = self.problems()
        self.assertTrue(any(needle in p for p in problems), problems)

    def test_clean(self):
        self.assertEqual(self.problems(), [])

    def test_main_with_upstream_dir(self):
        rc = drift.main(["--template", str(self.tpl), "--upstream-dir", str(self.up)])
        self.assertEqual(rc, 0)

    def test_crlf_is_not_a_difference(self):
        (self.tpl / "local/compose.yml").write_bytes(b"name: dev\r\n")
        self.assertEqual(self.problems(), [])

    def test_unexplained_content_drift(self):
        self.write(self.tpl, "src/main/java/com/example/app/A.java", "package com.example.app;\n\nclass A { int x; }\n")
        self.assert_problem("A.java: 写し元と違います")

    def test_rename_not_applied_in_template(self):
        self.write(self.tpl, "local/compose.yml", "name: com.example.sample\n")
        self.write(self.up, "local/compose.yml", "name: com.example.sample\n")
        self.assert_problem("local/compose.yml: 写し元と違います")

    def test_file_only_in_template(self):
        self.write(self.tpl, "src/main/resources/extra.yml", "a: 1\n")
        self.assert_problem("extra.yml: template にだけあります")

    def test_file_only_in_upstream(self):
        self.write(self.up, "sample-app/src/main/resources/new.yml", "a: 1\n")
        self.assert_problem("new.yml: 写し元にあるのに template にありません")

    def test_replace_with_extra_change(self):
        self.write(self.tpl, "settings.gradle", "rootProject.name = 'app'\ninclude 'x'\n")
        self.assert_problem("settings.gradle: 許可した置き換え以外の差分があります")

    def test_replace_source_gone(self):
        self.write(self.up, "sample-app/settings.gradle", "rootProject.name = 'app'\n")
        self.assert_problem("置き換え元 \"'sample-app'\" が写し元にありません")

    def test_keep_in_sync_version(self):
        self.write(self.up, "sample-app/build.gradle", "dependencies {\n    implementation 'a:b:2.0'\n}\n")
        self.assert_problem("揃える行がありません: implementation 'a:b:2.0'")

    def test_modified_but_identical_is_stale(self):
        self.write(self.tpl, "build.gradle", "dependencies {\n    implementation 'a:b:1.0'\n}\n")
        self.assert_problem("build.gradle: kind: modified ですが差分がありません")

    def test_unused_allowance(self):
        (self.up / "local/README.md").unlink()
        self.assert_problem("local/README.md: 許可（kind: removed）に当たる差分がありません")

    def test_config_requires_reason_and_full_sha(self):
        broken = CONFIG.replace("reason: 持ち込まない", "reason: ''").replace("0123", "main", 1)
        self.write(self.tpl, "UPSTREAM.yaml", broken)
        with self.assertRaises(ValueError) as cm:
            drift.load_config(self.tpl / "UPSTREAM.yaml")
        self.assertIn("reason", str(cm.exception))
        self.assertIn("40 桁", str(cm.exception))

    def test_fetch_pinned_sha_from_git_repo(self):
        repo = self.tmp / "remote"
        shutil.copytree(self.up, repo)
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "init"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "uploadpack.allowAnySHA1InWant", "true"], check=True)
        sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        cfg = (self.tpl / "UPSTREAM.yaml").read_text(encoding="utf-8")
        cfg = cfg.replace("example/upstream", repo.as_posix()).replace("0123456789abcdef0123456789abcdef01234567", sha)
        (self.tpl / "UPSTREAM.yaml").write_text(cfg, encoding="utf-8")
        self.assertEqual(drift.main(["--template", str(self.tpl)]), 0)

    def test_real_template_config_is_valid(self):
        cfg = drift.load_config(ROOT / "template/UPSTREAM.yaml")
        self.assertEqual(len(cfg.sha), 40)


if __name__ == "__main__":
    unittest.main()
