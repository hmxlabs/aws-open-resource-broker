"""Verify resilience strategies have no botocore dependency."""
import ast
import pathlib


def _get_imports(filepath: pathlib.Path) -> set[str]:
    """Extract all import module names from a Python file."""
    tree = ast.parse(filepath.read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports


def test_circuit_breaker_no_botocore():
    """circuit_breaker.py must not import botocore."""
    path = pathlib.Path("src/orb/infrastructure/resilience/strategy/circuit_breaker.py")
    imports = _get_imports(path)
    assert "botocore" not in imports, "circuit_breaker.py still imports botocore"


def test_exponential_no_botocore():
    """exponential.py must not import botocore."""
    path = pathlib.Path("src/orb/infrastructure/resilience/strategy/exponential.py")
    imports = _get_imports(path)
    assert "botocore" not in imports, "exponential.py still imports botocore"


def test_circuit_breaker_no_non_retryable_codes():
    """circuit_breaker.py must not have NON_RETRYABLE_CODES."""
    path = pathlib.Path("src/orb/infrastructure/resilience/strategy/circuit_breaker.py")
    source = path.read_text()
    assert "NON_RETRYABLE_CODES" not in source, "circuit_breaker.py still has NON_RETRYABLE_CODES"


def test_exponential_no_non_retryable_codes():
    """exponential.py must not have NON_RETRYABLE_CODES."""
    path = pathlib.Path("src/orb/infrastructure/resilience/strategy/exponential.py")
    source = path.read_text()
    assert "NON_RETRYABLE_CODES" not in source, "exponential.py still has NON_RETRYABLE_CODES"
