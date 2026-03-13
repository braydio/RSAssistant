"""Guard against drift between env loaders and documented env keys."""

from __future__ import annotations

import ast
import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_FILES = (
    REPO_ROOT / "utils" / "config_utils.py",
    REPO_ROOT / "rsassistant" / "bot" / "core.py",
    REPO_ROOT / "utils" / "policy_resolver.py",
    REPO_ROOT / "plugins" / "ultma" / "config" / "__init__.py",
)

ENV_EXAMPLE_PATH = REPO_ROOT / "config" / ".env.example"
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*=")

# config_utils helper wrappers that internally call os.getenv.
GETENV_WRAPPERS = {
    "_get_env_bool",
    "_get_env_int",
    "_get_env_float",
    "_resolve_path_env",
    "_resolve_dir_env",
}


class EnvDocumentationDriftTest(unittest.TestCase):
    """Ensure env keys used by loaders are represented in config/.env.example."""

    def test_documented_env_keys_cover_loader_keys(self) -> None:
        documented_keys = self._read_documented_env_keys(ENV_EXAMPLE_PATH)
        referenced_keys = self._read_referenced_env_keys(TARGET_FILES)

        missing_keys = sorted(referenced_keys - documented_keys)
        self.assertEqual(
            [],
            missing_keys,
            "Missing keys in config/.env.example: " + ", ".join(missing_keys),
        )

    @staticmethod
    def _read_documented_env_keys(path: Path) -> set[str]:
        keys: set[str] = set()
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or not ENV_KEY_RE.match(line):
                continue
            key, _value = line.split("=", 1)
            keys.add(key.strip())
        return keys

    @staticmethod
    def _read_referenced_env_keys(paths: tuple[Path, ...]) -> set[str]:
        keys: set[str] = set()
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                if not node.args:
                    continue

                env_key = EnvDocumentationDriftTest._extract_env_key(node.args[0])
                if not env_key:
                    continue

                if EnvDocumentationDriftTest._is_os_getenv_call(node):
                    keys.add(env_key)
                    continue

                if EnvDocumentationDriftTest._is_getenv_wrapper_call(node):
                    keys.add(env_key)
        return keys

    @staticmethod
    def _extract_env_key(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _is_os_getenv_call(node: ast.Call) -> bool:
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getenv"
        )

    @staticmethod
    def _is_getenv_wrapper_call(node: ast.Call) -> bool:
        func = node.func
        return isinstance(func, ast.Name) and func.id in GETENV_WRAPPERS


if __name__ == "__main__":
    unittest.main()
