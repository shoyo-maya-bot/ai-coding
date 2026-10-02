"""spec-trace — 仕様（要件）と実装・テストの対応表を検証し、裏付けのない「実装済み」「テスト済み」を検出する"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("spec-trace")
except PackageNotFoundError:
    __version__ = "0.0.0+local"
