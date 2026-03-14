"""Unit tests for init_command_handler — flow order and cache bypass."""

from unittest.mock import MagicMock, patch

import orb.interface.init_command_handler as _mod


def _make_strategy(regions=None, default_region="us-east-1"):
    strategy = MagicMock()
    strategy.get_available_regions.return_value = regions or []
    strategy.get_default_region.return_value = default_region
    strategy.get_available_credential_sources.return_value = [
        {"name": "default", "description": "Default profile"}
    ]
    strategy.test_credentials.return_value = {"success": True}
    strategy.get_credential_requirements.return_value = {}
    return strategy


def _mock_container():
    console = MagicMock()
    container = MagicMock()
    container.get.return_value = console
    return container


def test_discover_infrastructure_uses_fresh_strategy():
    """_discover_infrastructure must call create_strategy_by_type, not get_or_create_strategy."""
    mock_registry = MagicMock()
    mock_registry.ensure_provider_type_registered.return_value = True
    mock_strategy = MagicMock()
    mock_strategy.discover_infrastructure_interactive.return_value = {"vpc_id": "vpc-123"}
    mock_registry.create_strategy_by_type.return_value = mock_strategy

    # get_provider_registry is imported locally inside _discover_infrastructure,
    # so patch it at the source package.
    with (
        patch(
            "orb.providers.registry.provider_registry.ProviderRegistry",
        ),
        patch(
            "orb.providers.registry.get_provider_registry",
            return_value=mock_registry,
        ),
        patch(
            "orb.interface.init_command_handler.get_container",
            return_value=_mock_container(),
        ),
    ):
        result = _mod._discover_infrastructure("aws", "us-east-1", "my-profile")

    mock_registry.create_strategy_by_type.assert_called_once_with(
        "aws", {"region": "us-east-1", "profile": "my-profile"}
    )
    mock_registry.get_or_create_strategy.assert_not_called()
    assert result == {"vpc_id": "vpc-123"}


def test_interactive_setup_credentials_before_region():
    """Credential prompt must appear before region prompt in _interactive_setup."""
    call_order = []

    def fake_get_available_credential_sources(provider_type):
        call_order.append("credentials")
        return [{"name": "my-profile", "description": "My Profile"}]

    def fake_test_provider_credentials(provider_type, source, **kwargs):
        call_order.append("test_credentials")
        return True, ""

    def fake_pick_region(regions, default_region=""):
        call_order.append("region")
        return "us-east-1"

    # inputs: scheduler, provider, credential, discover?, add another?
    inputs = iter(["1", "1", "1", "N", "N"])

    with (
        patch.object(_mod, "get_container", return_value=_mock_container()),
        patch.object(
            _mod,
            "_get_available_schedulers",
            return_value=[
                {"type": "default", "display_name": "Default", "description": "Default scheduler"}
            ],
        ),
        patch.object(
            _mod,
            "_get_available_providers",
            return_value=[{"type": "aws", "display_name": "aws", "description": "AWS Provider"}],
        ),
        patch.object(
            _mod,
            "_get_available_credential_sources",
            side_effect=fake_get_available_credential_sources,
        ),
        patch.object(
            _mod, "_test_provider_credentials", side_effect=fake_test_provider_credentials
        ),
        patch.object(_mod, "_pick_region", side_effect=fake_pick_region),
        patch.object(_mod, "_get_provider_strategy", return_value=_make_strategy()),
        patch.object(_mod, "_discover_infrastructure", return_value={}),
        patch("builtins.input", side_effect=inputs),
    ):
        _mod._interactive_setup()

    assert "credentials" in call_order, f"credentials not called; order={call_order}"
    assert "region" in call_order, f"region not called; order={call_order}"
    cred_idx = call_order.index("credentials")
    region_idx = call_order.index("region")
    assert cred_idx < region_idx, (
        f"Expected credentials ({cred_idx}) before region ({region_idx}), got: {call_order}"
    )


def test_credentials_tested_without_region():
    """_test_provider_credentials must be called before region is collected."""
    test_creds_called_before_region = []
    region_collected = []

    def fake_test_provider_credentials(provider_type, source, **kwargs):
        if not region_collected:
            test_creds_called_before_region.append(True)
        return True, ""

    def fake_pick_region(regions, default_region=""):
        region_collected.append("us-east-1")
        return "us-east-1"

    # inputs: scheduler, provider, credential, discover?, add another?
    inputs = iter(["1", "1", "1", "N", "N"])

    with (
        patch.object(_mod, "get_container", return_value=_mock_container()),
        patch.object(
            _mod,
            "_get_available_schedulers",
            return_value=[
                {"type": "default", "display_name": "Default", "description": "Default scheduler"}
            ],
        ),
        patch.object(
            _mod,
            "_get_available_providers",
            return_value=[{"type": "aws", "display_name": "aws", "description": "AWS Provider"}],
        ),
        patch.object(
            _mod,
            "_get_available_credential_sources",
            return_value=[{"name": "my-profile", "description": "My Profile"}],
        ),
        patch.object(
            _mod, "_test_provider_credentials", side_effect=fake_test_provider_credentials
        ),
        patch.object(_mod, "_pick_region", side_effect=fake_pick_region),
        patch.object(_mod, "_get_provider_strategy", return_value=_make_strategy()),
        patch.object(_mod, "_discover_infrastructure", return_value={}),
        patch("builtins.input", side_effect=inputs),
    ):
        _mod._interactive_setup()

    assert test_creds_called_before_region, (
        "test_credentials was not called before region was collected"
    )
    assert region_collected, "region was never collected"
