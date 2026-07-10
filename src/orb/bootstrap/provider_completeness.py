"""Provider-completeness assertion for bootstrap.

Call :func:`assert_provider_registrations_complete` after all provider
registrations have run.  It checks that every type registered in
:class:`ProviderRegistry` also has an entry in every satellite registry that
new providers must populate.

This would have caught the Azure/GCP silent-registration bugs: a provider
that calls ``register_<name>_provider(registry)`` but omits
``initialize_<name>_provider()`` will be flagged immediately at startup rather
than silently returning ``None`` somewhere deep in a call chain.
"""

from __future__ import annotations


class ProviderCompletenessError(RuntimeError):
    """Raised when one or more providers have incomplete satellite registrations.

    The message lists every provider and every registry it is missing from so
    the operator knows exactly what to fix without inspecting code.
    """


def assert_provider_registrations_complete() -> None:
    """Assert that every ProviderRegistry type has all required satellite entries.

    Checked satellites (all must be populated for each provider type):
    - :class:`~orb.infrastructure.registry.cli_spec_registry.CLISpecRegistry`
    - :class:`~orb.infrastructure.scheduler.hostfactory.field_mapping_registry.FieldMappingRegistry`
    - :class:`~orb.providers.registry.defaults_loader_registry.DefaultsLoaderRegistry`
    - :class:`~orb.infrastructure.registry.template_extension_registry.TemplateExtensionRegistry`
      (checks ``has_extension``)
    - :class:`~orb.infrastructure.registry.template_example_generator_registry.TemplateExampleGeneratorRegistry`

    Raises:
        ProviderCompletenessError: when any provider is missing one or more
            satellite registrations.  The error message names every provider
            and every registry it is missing from.
    """
    from orb.infrastructure.registry.cli_spec_registry import CLISpecRegistry
    from orb.infrastructure.registry.template_example_generator_registry import (
        TemplateExampleGeneratorRegistry,
    )
    from orb.infrastructure.registry.template_extension_registry import TemplateExtensionRegistry
    from orb.infrastructure.scheduler.hostfactory.field_mapping_registry import FieldMappingRegistry
    from orb.providers.registry import get_provider_registry
    from orb.providers.registry.defaults_loader_registry import DefaultsLoaderRegistry

    registry = get_provider_registry()
    provider_types = registry.get_registered_types()

    # Map of human-readable registry name → callable that returns True when
    # the provider type is registered in that satellite.
    satellite_checks: list[tuple[str, object]] = [
        ("CLISpecRegistry", CLISpecRegistry),
        ("FieldMappingRegistry", FieldMappingRegistry),
        ("DefaultsLoaderRegistry", DefaultsLoaderRegistry),
        ("TemplateExtensionRegistry", TemplateExtensionRegistry),
        ("TemplateExampleGeneratorRegistry", TemplateExampleGeneratorRegistry),
    ]

    gaps: list[str] = []

    for provider_type in sorted(provider_types):
        missing: list[str] = []

        for registry_name, sat_registry in satellite_checks:
            if registry_name == "TemplateExtensionRegistry":
                # TemplateExtensionRegistry uses has_extension() rather than
                # a direct get_or_none because it manages two internal dicts
                # (class-based and instance-based extensions).
                registered = sat_registry.has_extension(provider_type)  # type: ignore[union-attr]
            else:
                registered = sat_registry.get_or_none(provider_type) is not None  # type: ignore[union-attr]

            if not registered:
                missing.append(registry_name)

        if missing:
            gaps.append(f"  provider={provider_type!r}: missing in [{', '.join(missing)}]")

    if gaps:
        lines = ["Provider registration is incomplete — satellite registries not populated:"]
        lines.extend(gaps)
        lines.append(
            "Fix: ensure initialize_<provider>_provider() is called during bootstrap "
            "for each registered provider type."
        )
        raise ProviderCompletenessError("\n".join(lines))
