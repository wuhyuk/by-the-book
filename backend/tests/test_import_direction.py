"""rules/가 llm/·api/를 import하지 않는지 AST로 검사한다 (CLAUDE.md 4절)."""

import ast
from pathlib import Path

import pytest

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
FORBIDDEN = ("llm", "api")


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 상대 import는 rules 안이므로 허용하되, 대상 이름은 검사
                names += [f".{node.module or ''}"]
            elif node.module:
                names.append(node.module)
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in (
            "__import__",
            "import_module",
        ):
            names += [a.value for a in node.args if isinstance(a, ast.Constant)]
    return names


RULE_FILES = sorted(RULES_DIR.glob("*.py"))


def test_rules_files_found() -> None:
    assert {p.name for p in RULE_FILES} >= {
        "money.py",
        "loader.py",
        "gym.py",
        "gym_display.py",
        "badge.py",
    }


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.name)
def test_rules_do_not_import_llm_or_api(path: Path) -> None:
    for name in imported_modules(path):
        top = name.lstrip(".").split(".")[0]
        assert top not in FORBIDDEN, f"{path.name}: {name}"
        if name.startswith("."):
            assert top in {"", "money", "loader", "gym", "badge", "gym_display"}, (
                f"{path.name}: {name}"
            )


def test_detector_catches_forbidden_import(tmp_path: Path) -> None:
    """검사기 자체가 금지된 import를 잡는지 확인한다."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import llm.adapter\nfrom api import health\n__import__('llm')\n",
        encoding="utf-8",
    )
    tops = {n.split(".")[0] for n in imported_modules(bad)}
    assert {"llm", "api"} <= tops
