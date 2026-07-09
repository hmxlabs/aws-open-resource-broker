"""Unit tests for the provider-completeness assertion.

Tests:
(a) A fully-populated provider passes the assertion without raising.
(b) A provider missing one or more satellite registrations raises
    ProviderCompletenessError naming each gap.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orb.bootstrap.provider_completeness import (
    ProviderCompletenessError,
    assert_provider_registrations_complete,
)

# Patch targets — the symbols are imported inside the function body so we patch
# them at their definition module, not at the provider_completeness module.
_PATCH_GET_REGISTRY = "orb.providers.registry.get_provider_registry"
_PATCH_CLI = "orb.infrastructure.registry.cli_spec_registry.CLISpecRegistry"
_PATCH_FM = "orb.infrastructure.scheduler.hostfactory.field_mapping_registry.FieldMappingRegistry"
_PATCH_DL = "orb.providers.registry.defaults_loader_registry.DefaultsLoaderRegistry"
_PATCH_TE = "orb.infrastructure.registry.template_extension_registry.TemplateExtensionRegistry"
_PATCH_EG = (
    "orb.infrastructure.registry.template_example_generator_registry"
    ".TemplateExampleGeneratorRegistry"
)


def _make_mock_provider_registry(*provider_types: str) -> MagicMock:
    """Return a mock ProviderRegistry-like object pre-loaded with *provider_types*."""
    mock_registry = MagicMock()
    mock_registry.get_registered_types.return_value = list(provider_types)
    return mock_registry


def _all_present_cli() -> MagicMock:
    m = MagicMock()
    m.get_or_none.return_value = MagicMock()
    return m


def _all_present_fm() -> MagicMock:
    m = MagicMock()
    m.get_or_none.return_value = MagicMock()
    return m


def _all_present_dl() -> MagicMock:
    m = MagicMock()
    m.get_or_none.return_value = MagicMock()
    return m


def _all_present_te() -> MagicMock:
    m = MagicMock()
    m.has_extension.return_value = True
    return m


def _all_present_eg() -> MagicMock:
    m = MagicMock()
    m.get_or_none.return_value = MagicMock()
    return m


class TestProviderCompletenessAssertionPasses:
    """Assertion should not raise when all satellites are populated."""

    def test_complete_single_provider(self) -> None:
        """A provider with all satellites registered passes silently."""
        mock_registry = _make_mock_provider_registry("testprov")

        with (
            patch(_PATCH_GET_REGISTRY, return_value=mock_registry),
            patch(_PATCH_CLI, _all_present_cli()),
            patch(_PATCH_FM, _all_present_fm()),
            patch(_PATCH_DL, _all_present_dl()),
            patch(_PATCH_TE, _all_present_te()),
            patch(_PATCH_EG, _all_present_eg()),
        ):
            # Must not raise
            assert_provider_registrations_complete()

    def test_no_providers_registered_passes(self) -> None:
        """An empty ProviderRegistry passes trivially — nothing to check."""
        mock_registry = _make_mock_provider_registry()  # no providers

        with patch(_PATCH_GET_REGISTRY, return_value=mock_registry):
            # Must not raise — no providers means no satellites to verify
            assert_provider_registrations_complete()

    def test_multiple_complete_providers_pass(self) -> None:
        """Two fully-registered providers both pass."""
        mock_registry = _make_mock_provider_registry("alpha", "beta")

        with (
            patch(_PATCH_GET_REGISTRY, return_value=mock_registry),
            patch(_PATCH_CLI, _all_present_cli()),
            patch(_PATCH_FM, _all_present_fm()),
            patch(_PATCH_DL, _all_present_dl()),
            patch(_PATCH_TE, _all_present_te()),
            patch(_PATCH_EG, _all_present_eg()),
        ):
            assert_provider_registrations_complete()


class TestProviderCompletenessAssertionFails:
    """Assertion must raise ProviderCompletenessError when satellites are missing."""

    def test_single_missing_satellite_raises(self) -> None:
        """A provider missing one satellite raises with the right registry name."""
        mock_registry = _make_mock_provider_registry("myprov")

        cli_mock = MagicMock()
        cli_mock.get_or_none.return_value = None  # CLISpec missing

        with (
            patch(_PATCH_GET_REGISTRY, return_value=mock_registry),
            patch(_PATCH_CLI, cli_mock),
            patch(_PATCH_FM, _all_present_fm()),
            patch(_PATCH_DL, _all_present_dl()),
            patch(_PATCH_TE, _all_present_te()),
            patch(_PATCH_EG, _all_present_eg()),
        ):
            with pytest.raises(ProviderCompletenessError) as exc_info:
                assert_provider_registrations_complete()

        error_message = str(exc_info.value)
        assert "myprov" in error_message
        assert "CLISpecRegistry" in error_message
        # FieldMappingRegistry was present — should not appear as a gap
        assert "FieldMappingRegistry" not in error_message

    def test_multiple_missing_satellites_all_named(self) -> None:
        """A provider missing multiple satellites lists all of them in the error."""
        mock_registry = _make_mock_provider_registry("newprov")

        cli_mock = MagicMock()
        cli_mock.get_or_none.return_value = None
        fm_mock = MagicMock()
        fm_mock.get_or_none.return_value = None
        dl_mock = MagicMock()
        dl_mock.get_or_none.return_value = None
        te_mock = MagicMock()
        te_mock.has_extension.return_value = False
        eg_mock = MagicMock()
        eg_mock.get_or_none.return_value = None

        with (
            patch(_PATCH_GET_REGISTRY, return_value=mock_registry),
            patch(_PATCH_CLI, cli_mock),
            patch(_PATCH_FM, fm_mock),
            patch(_PATCH_DL, dl_mock),
            patch(_PATCH_TE, te_mock),
            patch(_PATCH_EG, eg_mock),
        ):
            with pytest.raises(ProviderCompletenessError) as exc_info:
                assert_provider_registrations_complete()

        error_message = str(exc_info.value)
        assert "newprov" in error_message
        assert "CLISpecRegistry" in error_message
        assert "FieldMappingRegistry" in error_message
        assert "DefaultsLoaderRegistry" in error_message
        assert "TemplateExtensionRegistry" in error_message
        assert "TemplateExampleGeneratorRegistry" in error_message

    def test_mixed_complete_and_incomplete_providers(self) -> None:
        """Only the incomplete provider's name appears in the error."""
        mock_registry = _make_mock_provider_registry("complete_prov", "incomplete_prov")

        # CLI spec only for complete_prov; everything else present for both
        cli_mock = MagicMock()
        cli_mock.get_or_none.side_effect = lambda key: (
            MagicMock() if key == "complete_prov" else None
        )

        with (
            patch(_PATCH_GET_REGISTRY, return_value=mock_registry),
            patch(_PATCH_CLI, cli_mock),
            patch(_PATCH_FM, _all_present_fm()),
            patch(_PATCH_DL, _all_present_dl()),
            patch(_PATCH_TE, _all_present_te()),
            patch(_PATCH_EG, _all_present_eg()),
        ):
            with pytest.raises(ProviderCompletenessError) as exc_info:
                assert_provider_registrations_complete()

        error_message = str(exc_info.value)
        # incomplete_prov is named in the gap list
        assert "incomplete_prov" in error_message
        assert "CLISpecRegistry" in error_message
        # complete_prov should NOT be listed as a gap provider — the line
        # format is "provider='<name>':", so we check for that exact pattern.
        assert "provider='complete_prov'" not in error_message

    def test_error_message_names_provider_and_fix_hint(self) -> None:
        """Error message includes the provider type and a fix hint."""
        mock_registry = _make_mock_provider_registry("orphanprov")

        cli_mock = MagicMock()
        cli_mock.get_or_none.return_value = None  # missing

        with (
            patch(_PATCH_GET_REGISTRY, return_value=mock_registry),
            patch(_PATCH_CLI, cli_mock),
            patch(_PATCH_FM, _all_present_fm()),
            patch(_PATCH_DL, _all_present_dl()),
            patch(_PATCH_TE, _all_present_te()),
            patch(_PATCH_EG, _all_present_eg()),
        ):
            with pytest.raises(ProviderCompletenessError) as exc_info:
                assert_provider_registrations_complete()

        error_message = str(exc_info.value)
        assert "orphanprov" in error_message
        # Should hint at initialize_<provider>_provider as the fix
        assert "initialize_" in error_message
