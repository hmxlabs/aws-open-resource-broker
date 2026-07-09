"""Observability (OpenTelemetry) configuration schema.

Standard ``OTEL_*`` environment variables take precedence over file-level
values.  This is the industry-standard "env wins" rule: operators can
override any file setting without rebuilding an image.  The override logic
lives in the ``_apply_otel_env_overrides`` model validator so it runs
automatically after Pydantic validation.

Honoured env vars:
  OTEL_SDK_DISABLED          → ``enabled`` (True when var == "true", else False)
  OTEL_EXPORTER_OTLP_ENDPOINT→ ``otlp_endpoint``
  OTEL_SERVICE_NAME          → ``service_name``
  OTEL_TRACES_SAMPLER_ARG    → ``traces_sample_rate`` (parsed as float)
"""

import os
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OtelConfig(BaseModel):
    """OpenTelemetry configuration.

    ``enabled`` defaults to ``False`` so that the SDK is **never** activated
    unless explicitly opted in.  When disabled, the :func:`configure_telemetry`
    bootstrap call is a complete no-op.

    ``metrics_exporters`` accepts a list so that multiple exporters can be
    active simultaneously:
      - ``"prometheus"`` — wires a ``PrometheusMetricReader`` against the
        global ``prometheus_client.REGISTRY`` (works with the existing
        ``/metrics`` FastAPI route).
      - ``"otlp"`` — wires a ``PeriodicExportingMetricReader`` that pushes
        to the OTLP endpoint specified by ``otlp_endpoint``.

    Both entries can coexist in the list.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(False, description="Enable OpenTelemetry SDK initialisation")
    metrics_exporters: list[str] = Field(
        default_factory=list,
        description=(
            "Active metrics exporters. Valid values: 'prometheus', 'otlp'. "
            "Multiple entries are supported simultaneously."
        ),
    )
    traces_exporter: Optional[str] = Field(
        None,
        description="Traces exporter. Valid values: 'otlp', None (no traces).",
    )
    otlp_endpoint: Optional[str] = Field(
        None,
        description=(
            "Base OTLP endpoint URL (e.g. 'http://localhost:4317'). "
            "Used by both the OTLP metrics exporter and the OTLP span exporter."
        ),
    )
    service_name: str = Field(
        "orb",
        description="OpenTelemetry service.name resource attribute.",
    )
    traces_sample_rate: float = Field(
        0.1,
        description="TraceIdRatioBased sampler argument (0.0–1.0).",
        ge=0.0,
        le=1.0,
    )

    @model_validator(mode="after")
    def _apply_otel_env_overrides(self) -> "OtelConfig":
        """Apply standard OTEL_* environment variable overrides (env wins).

        This runs after Pydantic has validated the file-sourced values.  Any
        ``OTEL_*`` variable that is set in the environment overrides the
        corresponding field.  Unset variables leave the field unchanged.
        """
        # OTEL_SDK_DISABLED: "true" (case-insensitive) disables the SDK.
        sdk_disabled = os.environ.get("OTEL_SDK_DISABLED", "").strip().lower()
        if sdk_disabled == "true":
            object.__setattr__(self, "enabled", False)

        # OTEL_EXPORTER_OTLP_ENDPOINT overrides otlp_endpoint.
        otlp_env = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if otlp_env:
            object.__setattr__(self, "otlp_endpoint", otlp_env)

        # OTEL_SERVICE_NAME overrides service_name.
        svc_name = os.environ.get("OTEL_SERVICE_NAME", "").strip()
        if svc_name:
            object.__setattr__(self, "service_name", svc_name)

        # OTEL_TRACES_SAMPLER_ARG overrides traces_sample_rate (parsed as float).
        sampler_arg = os.environ.get("OTEL_TRACES_SAMPLER_ARG", "").strip()
        if sampler_arg:
            try:
                rate = float(sampler_arg)
                rate = max(0.0, min(1.0, rate))
                object.__setattr__(self, "traces_sample_rate", rate)
            except ValueError:
                pass  # Ignore unparseable values; keep the file/default value.

        return self
