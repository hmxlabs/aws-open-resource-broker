"""Tests for configure_telemetry() bootstrap function.

Scope:
  1. enabled=False → no-op (no provider set, no raise).
  2. SDK absent (ImportError path) → no-op, no raise.
  3. Idempotency — second call is a no-op.
  4. _reset_telemetry_state() re-arms the idempotency flag.

Note: These tests do NOT attempt to build real OTel providers because the
SDK may not be installed in every test environment (the [monitoring] extra is
optional).  The tests validate the guard logic, not the SDK internals.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

import orb.bootstrap.telemetry as telemetry_module
from orb.bootstrap.telemetry import _reset_telemetry_state, configure_telemetry
from orb.config.schemas.observability_schema import OtelConfig
from orb.domain.base.ports.logging_port import LoggingPort
from orb.infrastructure.di.container import DIContainer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_container_with_otel(otel_config: OtelConfig) -> DIContainer:
    """Build a minimal DIContainer whose ConfigurationPort returns otel_config."""
    container = DIContainer()

    mock_logger = Mock(spec=LoggingPort)
    container.register_instance(LoggingPort, mock_logger)

    # Build a mock AppConfig that carries the given OtelConfig.
    mock_app_config = MagicMock()
    mock_app_config.observability = otel_config

    # Build a mock ConfigurationPort whose get_typed(AppConfig) returns mock_app_config.
    from orb.domain.base.ports.configuration_port import ConfigurationPort

    mock_config_port = MagicMock(spec=ConfigurationPort)
    mock_config_port.get_typed.return_value = mock_app_config
    container.register_instance(ConfigurationPort, mock_config_port)

    return container


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry state before and after every test for isolation."""
    _reset_telemetry_state()
    yield
    _reset_telemetry_state()


# ---------------------------------------------------------------------------
# Test: enabled=False is a no-op
# ---------------------------------------------------------------------------


class TestConfigureTelemetryDisabled:
    """When otel.enabled is False configure_telemetry must be a complete no-op."""

    def test_does_not_raise_when_disabled(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))
        # Must not raise under any circumstances.
        configure_telemetry(container)

    def test_does_not_set_meter_provider_when_disabled(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))
        with patch("opentelemetry.metrics.set_meter_provider") as mock_set:
            configure_telemetry(container)
        mock_set.assert_not_called()

    def test_does_not_set_tracer_provider_when_disabled(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))
        with patch("opentelemetry.trace.set_tracer_provider") as mock_set:
            configure_telemetry(container)
        mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# Test: SDK absent (ImportError path)
# ---------------------------------------------------------------------------


class TestConfigureTelemetrySDKAbsent:
    """configure_telemetry must not raise when the OTel SDK is not installed."""

    def test_no_raise_when_sdk_import_fails(self):
        """Simulate SDK absence by patching the import inside configure_telemetry."""
        container = _make_container_with_otel(OtelConfig(enabled=True))

        # Patch the builtins so that importing 'opentelemetry.sdk.metrics' fails.
        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )  # type: ignore[union-attr]

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.startswith("opentelemetry.sdk") or name.startswith("opentelemetry.exporter"):
                raise ImportError(f"Simulated missing package: {name}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            # Must complete without raising.
            try:
                configure_telemetry(container)
            except ImportError:
                pytest.fail(
                    "configure_telemetry raised ImportError — the SDK-absent guard is broken"
                )

    def test_no_raise_when_top_level_otel_missing(self, monkeypatch):
        """Simulate total opentelemetry absence via sys.modules manipulation."""
        container = _make_container_with_otel(OtelConfig(enabled=True))

        # Remove opentelemetry from sys.modules so the import fails.
        otel_keys = [k for k in sys.modules if k.startswith("opentelemetry")]
        saved = {k: sys.modules.pop(k) for k in otel_keys}

        # Make any opentelemetry import fail.
        monkeypatch.setitem(sys.modules, "opentelemetry", None)  # type: ignore[arg-type]

        try:
            configure_telemetry(container)
        except Exception as exc:
            pytest.fail(f"configure_telemetry raised unexpectedly: {exc}")
        finally:
            # Restore to avoid contaminating other tests.
            for k, v in saved.items():
                sys.modules[k] = v
            monkeypatch.delitem(sys.modules, "opentelemetry", raising=False)


# ---------------------------------------------------------------------------
# Test: Idempotency
# ---------------------------------------------------------------------------


class TestConfigureTelemetryIdempotency:
    """A second call to configure_telemetry must be a complete no-op."""

    def test_second_call_is_noop(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))

        # We can verify idempotency by checking the module flag directly.
        configure_telemetry(container)
        assert telemetry_module._telemetry_configured is True

        # Patch set_meter_provider to verify it's not called on the second run.
        with patch("opentelemetry.metrics.set_meter_provider") as mock_set:
            configure_telemetry(container)
        mock_set.assert_not_called()

    def test_flag_set_after_first_call(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))
        assert telemetry_module._telemetry_configured is False
        configure_telemetry(container)
        assert telemetry_module._telemetry_configured is True

    def test_reset_re_arms_flag(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))
        configure_telemetry(container)
        assert telemetry_module._telemetry_configured is True
        _reset_telemetry_state()
        assert telemetry_module._telemetry_configured is False

    def test_after_reset_call_runs_again(self):
        container = _make_container_with_otel(OtelConfig(enabled=False))
        configure_telemetry(container)
        _reset_telemetry_state()

        # After reset, the function should run (and complete without error).
        configure_telemetry(container)
        assert telemetry_module._telemetry_configured is True
