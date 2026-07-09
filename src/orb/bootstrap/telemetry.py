"""OpenTelemetry bootstrap for the Open Resource Broker.

This module is the single call-site for OTel SDK initialisation.
It is designed to be:

  * **No-op safe** — safe to call even when ``opentelemetry-sdk`` is not
    installed, or when ``otel.enabled`` is ``False`` (the default).
  * **Idempotent** — a second call is silently ignored so that tests or
    re-entrant bootstrap paths cannot accidentally install a second
    MeterProvider / TracerProvider.  The flag is reset by
    ``_reset_telemetry_state()`` which ``DIContainer.reset()`` calls for
    test isolation.
  * **Import-guard style** — the SDK import is wrapped in ``try/except
    ImportError``, matching the silent-skip pattern used elsewhere in
    ``core_services.py`` (the SSE handler guard at the bottom of
    ``create_event_bus``).

MeterProvider construction:
  Multiple metric readers are built from ``otel_config.metrics_exporters``:
    - ``"prometheus"`` → ``PrometheusMetricReader()`` (registers against the
      global ``prometheus_client.REGISTRY``; coexists with the existing
      ``/metrics`` FastAPI route).
    - ``"otlp"``       → ``PeriodicExportingMetricReader(
                              OTLPMetricExporter(endpoint=otlp_endpoint)
                          )``.
  Both can be active simultaneously.

TracerProvider construction:
  When ``traces_exporter == "otlp"`` a ``BatchSpanProcessor`` with an
  ``OTLPSpanExporter`` is installed.  A ``TraceIdRatioBased`` sampler is
  always applied using ``traces_sample_rate``.

Call site: ``bootstrap/services.py`` — immediately after
``register_core_services(container)`` and before any Meter or CQRS handler
is acquired.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orb.infrastructure.di.container import DIContainer

# Module-level idempotency flag.  Set to True after the first successful
# (or intentionally skipped) call to configure_telemetry().
_telemetry_configured: bool = False


def _reset_telemetry_state() -> None:
    """Reset the idempotency flag so the next call re-runs configuration.

    Called by ``DIContainer.reset()`` so each test starts with a clean state.
    """
    global _telemetry_configured
    _telemetry_configured = False


def configure_telemetry(container: "DIContainer") -> None:  # noqa: C901
    """Initialise the OTel SDK from the container's OtelConfig.

    This function is a complete no-op in any of the following situations:
      1. Already called once (idempotency guard).
      2. ``opentelemetry-sdk`` is not installed (guarded ``ImportError``).
      3. ``otel_config.enabled`` is ``False`` (the default).

    When enabled and the SDK is present, it:
      - Builds a ``MeterProvider`` with all configured metric readers.
      - Installs it as the global OTel metrics provider.
      - Builds a ``TracerProvider`` with a ratio sampler and (optionally) an
        OTLP span exporter.
      - Installs it as the global OTel tracer provider.

    Args:
        container: The application DI container (used to resolve AppConfig).
    """
    global _telemetry_configured

    if _telemetry_configured:
        return

    # Mark as configured regardless of what happens below, so we never
    # attempt a partial second initialisation on re-entry.
    _telemetry_configured = True

    # --- guard: SDK may not be installed ---
    try:
        from opentelemetry import metrics, trace  # noqa: F401 (availability probe)
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError:
        # opentelemetry-sdk not installed; silently skip (no-op default).
        return

    # --- resolve OtelConfig from the container ---
    try:
        from orb.config.schemas.app_schema import AppConfig
        from orb.domain.base.ports.configuration_port import ConfigurationPort

        config_port = container.get(ConfigurationPort)
        app_config: AppConfig = config_port.get_typed(AppConfig)  # type: ignore[arg-type]
        otel_config = app_config.observability
    except Exception:
        # Config resolution failed; stay no-op rather than crash.
        return

    if not otel_config.enabled:
        return

    resource = Resource.create({SERVICE_NAME: otel_config.service_name})

    # --- MeterProvider ---
    metric_readers: list[object] = []

    for exporter_name in otel_config.metrics_exporters:
        if exporter_name == "prometheus":
            try:
                from opentelemetry.exporter.prometheus import (  # type: ignore[import-not-found]
                    PrometheusMetricReader,
                )

                metric_readers.append(PrometheusMetricReader())
            except ImportError:
                pass  # opentelemetry-exporter-prometheus not installed; skip.

        elif exporter_name == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (  # type: ignore[import-not-found]
                    OTLPMetricExporter,
                )
                from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

                kwargs: dict = {}
                if otel_config.otlp_endpoint:
                    kwargs["endpoint"] = otel_config.otlp_endpoint
                metric_readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(**kwargs)))
            except ImportError:
                pass  # OTLP exporter not installed; skip.

    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)  # type: ignore[arg-type]
    metrics.set_meter_provider(meter_provider)

    # --- TracerProvider ---
    try:
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        sampler = TraceIdRatioBased(otel_config.traces_sample_rate)
        tracer_provider = TracerProvider(resource=resource, sampler=sampler)

        if otel_config.traces_exporter == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
                    OTLPSpanExporter,
                )
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                exporter_kwargs: dict = {}
                if otel_config.otlp_endpoint:
                    exporter_kwargs["endpoint"] = otel_config.otlp_endpoint
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(**exporter_kwargs))
                )
            except ImportError:
                pass  # OTLP span exporter not installed; skip.

        trace.set_tracer_provider(tracer_provider)
    except ImportError:
        pass  # Trace SDK not available; metrics-only setup still active.
