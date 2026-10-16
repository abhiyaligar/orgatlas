"""Single source of truth for the pinned tree-sitter parser set.

Both ``backend/requirements.txt`` and ``e2b_template.py`` consume this list, so
the sandbox can never be built with different grammar versions than the host
runs its tests against.

Every version here was confirmed to publish an ``abi3`` or CPython 3.11
``manylinux_x86_64`` wheel, which is what the E2B image needs.
"""

from __future__ import annotations

# tree-sitter core must be pinned explicitly: the grammar packages declare it
# only as an optional ``[core]`` extra, so a plain install would not pull it in.
TREE_SITTER_CORE = "tree-sitter~=0.26"

TREE_SITTER_GRAMMARS = (
    "tree-sitter-rust==0.24.2",
    "tree-sitter-c==0.24.2",
    "tree-sitter-cpp==0.23.4",
    "tree-sitter-python==0.25.0",
    "tree-sitter-javascript==0.25.0",
    "tree-sitter-typescript==0.23.2",
    "tree-sitter-go==0.25.0",
    "tree-sitter-java==0.23.5",
    "tree-sitter-yaml==0.7.2",
    "tree-sitter-toml==0.7.0",
)

TREE_SITTER_PACKAGES = (TREE_SITTER_CORE, *TREE_SITTER_GRAMMARS)


def pip_requirements() -> list[str]:
    return list(TREE_SITTER_PACKAGES)


def requirements_txt_block() -> str:
    """The block appended to backend/requirements.txt."""
    lines = ["", "# Syntax extraction. Pinned via e2b_template.py so the sandbox", "# template and the local venv cannot diverge."]
    lines += [f"{package}" for package in TREE_SITTER_PACKAGES]
    return "\n".join(lines) + "\n"


SMOKE_TEST = r"""
import importlib, sys
from tree_sitter import Language, Parser

LOADERS = {
    "tree_sitter_rust": ["language"],
    "tree_sitter_c": ["language"],
    "tree_sitter_cpp": ["language"],
    "tree_sitter_python": ["language"],
    "tree_sitter_javascript": ["language"],
    "tree_sitter_typescript": ["language_typescript", "language_tsx"],
    "tree_sitter_go": ["language"],
    "tree_sitter_java": ["language"],
    "tree_sitter_yaml": ["language"],
    "tree_sitter_toml": ["language"],
}

failures = []
for module_name, loaders in LOADERS.items():
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        failures.append(f"{module_name}: import failed: {exc}")
        continue
    for loader in loaders:
        try:
            language = Language(getattr(module, loader)())
            Parser(language).parse(b"x")
        except Exception as exc:
            failures.append(f"{module_name}.{loader}: {type(exc).__name__}: {exc}")

if failures:
    print("GRAMMAR SMOKE TEST FAILED")
    for line in failures:
        print("  -", line)
    sys.exit(1)
print(f"grammar smoke test passed: {sum(len(v) for v in LOADERS.values())} loaders")
"""