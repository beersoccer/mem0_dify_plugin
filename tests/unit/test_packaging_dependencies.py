import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIFY_PLUGIN_DEPENDENCY = "dify-plugin==0.7.1"


def test_dify_plugin_sdk_is_pinned_consistently():
    requirement_lines = {
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert DIFY_PLUGIN_DEPENDENCY in requirement_lines
    assert DIFY_PLUGIN_DEPENDENCY in pyproject["project"]["dependencies"]
