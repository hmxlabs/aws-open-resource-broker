"""Verify init_command_handler has no AWS-specific code."""
import ast
import pathlib


def _get_source():
    return pathlib.Path("src/orb/interface/init_command_handler.py").read_text()


def _get_imports(filepath: pathlib.Path) -> set[str]:
    tree = ast.parse(filepath.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_no_aws_provider_imports():
    """init_command_handler must not import from orb.providers.aws."""
    imports = _get_imports(pathlib.Path("src/orb/interface/init_command_handler.py"))
    aws_imports = [m for m in imports if "providers.aws" in m]
    assert not aws_imports, f"AWS imports found: {aws_imports}"


def test_no_common_aws_regions_constant():
    """_COMMON_AWS_REGIONS must not exist in init_command_handler."""
    source = _get_source()
    assert "_COMMON_AWS_REGIONS" not in source, "_COMMON_AWS_REGIONS still in init_command_handler"


def test_no_provider_type_aws_branching():
    """No 'if provider_type == \"aws\"' branching."""
    source = _get_source()
    assert 'provider_type == "aws"' not in source, "AWS provider branching still present"
    assert "provider_type == 'aws'" not in source, "AWS provider branching still present"


def test_provider_strategy_has_get_available_regions():
    """Base ProviderStrategy must have get_available_regions method."""
    from orb.providers.base.strategy.provider_strategy import ProviderStrategy
    assert hasattr(ProviderStrategy, "get_available_regions"), "get_available_regions not on ProviderStrategy"
