"""Provider selection policy — extracted from ProviderRegistry into a dedicated service.

This service holds the ~430-line provider-selection and load-balancing block that
previously lived in ProviderRegistry.  It depends only on domain port abstractions
(ProviderRegistryPort + ConfigurationPort), so there is no circular dependency:

    ProviderSelectionService (infrastructure)
        → ProviderRegistryPort  (domain port)
        → ConfigurationPort     (domain port)

ProviderRegistry (infrastructure) injects this service and delegates the two
public selection methods to it, keeping ProviderRegistry focused on registration
and strategy-lifecycle concerns only.
"""

from typing import Any, List, Optional

from orb.domain.base.ports.configuration_port import ConfigurationPort
from orb.domain.base.ports.provider_registry_port import ProviderRegistryPort
from orb.domain.base.results import ProviderSelectionResult
from orb.infrastructure.logging.logger import get_logger


class ProviderSelectionService:
    """Infrastructure service implementing provider-selection and load-balancing policy.

    Constructed with a ProviderRegistryPort (for cached-strategy lookups) and a
    ConfigurationPort (for reading active-provider lists and selection policy).
    Neither port dependency creates a cycle because both are domain-layer abstractions
    that sit below infrastructure.
    """

    def __init__(
        self,
        registry: ProviderRegistryPort,
        config_port: ConfigurationPort,
    ) -> None:
        self._registry = registry
        self._config_port = config_port
        self._logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public selection entry points (mirror ProviderRegistryPort contract)
    # ------------------------------------------------------------------

    def select_provider_for_template(
        self, template: Any, provider_name: Optional[str] = None, logger: Optional[Any] = None
    ) -> ProviderSelectionResult:
        """Select provider instance for template requirements.

        Selection hierarchy:
        1. CLI override (--provider-name flag)
        2. Explicit provider instance (template.provider_name)
        3. Provider type with load balancing (template.provider_type)
        4. Auto-selection based on API capabilities (template.provider_api)
        5. Fallback to configuration default
        """
        if logger:
            logger.info(
                "Selecting provider for template: %s", getattr(template, "template_id", "unknown")
            )

        # Strategy 1: CLI override (highest precedence)
        effective_provider = provider_name or self._get_cli_override()
        if effective_provider:
            return self._select_by_cli_override(template, effective_provider, logger)

        # Strategy 2: Explicit provider instance selection
        if hasattr(template, "provider_name") and template.provider_name:
            return self._select_by_explicit_provider(template, logger)

        # Strategy 3: Provider type with load balancing
        if hasattr(template, "provider_type") and template.provider_type:
            return self._select_by_provider_type(template, logger)

        # Strategy 4: Auto-selection based on API capabilities
        if hasattr(template, "provider_api") and template.provider_api:
            return self._select_by_api_capability(template, logger)

        # Strategy 5: Fallback to default
        return self._select_default_provider(template, logger)

    def select_active_provider(
        self,
        logger: Optional[Any] = None,
        *,
        provider_name: Optional[str] = None,
        provider_type: Optional[str] = None,
    ) -> ProviderSelectionResult:
        """Select active provider instance from configuration.

        Precedence:
        1. provider_name argument — exact instance lookup.
        2. provider_type argument — filter active instances by type,
           then apply load-balancing over the filtered set.
        3. Default behaviour — load-balance across all active instances.
        """
        if logger:
            logger.debug("Selecting active provider using selection policy")

        name_override = provider_name
        type_override = provider_type

        if name_override:
            provider_instance = self._get_provider_instance_config(name_override)
            if not provider_instance:
                raise ValueError(f"Provider instance '{name_override}' not found in configuration")
            if not provider_instance.enabled:
                raise ValueError(f"Provider instance '{name_override}' is disabled")
            if logger:
                logger.info("Selected provider by name override: %s", name_override)
            return ProviderSelectionResult(
                provider_type=provider_instance.type,
                provider_name=name_override,
                selection_reason="CLI name override (--provider-name)",
                confidence=1.0,
            )

        provider_config = self._get_provider_config()
        if not provider_config:
            raise ValueError("No provider configuration available")

        active_providers = provider_config.get_active_providers()
        if not active_providers:
            raise ValueError("No active providers found in configuration")

        if type_override:
            filtered = [p for p in active_providers if p.type == type_override]
            if not filtered:
                raise ValueError(f"No active providers of type '{type_override}'")
            if len(filtered) == 1:
                selected = filtered[0]
                reason = f"CLI type override (--provider-type {type_override}) single_active_match"
            else:
                selected = self._apply_load_balancing_strategy(
                    filtered, provider_config.selection_policy
                )
                reason = (
                    f"CLI type override (--provider-type {type_override}) "
                    f"load_balanced_{provider_config.selection_policy.lower()}"
                )
            if logger:
                logger.info(
                    "Selected provider by type override '%s': %s", type_override, selected.name
                )
            return ProviderSelectionResult(
                provider_type=selected.type,
                provider_name=selected.name,
                selection_reason=reason,
                confidence=1.0,
                alternatives=[p.name for p in filtered if p.name != selected.name],
            )

        if len(active_providers) == 1:
            selected = active_providers[0]
            reason = "single_active_provider"
        else:
            selected = self._apply_load_balancing_strategy(
                active_providers, provider_config.selection_policy
            )
            reason = f"load_balanced_{provider_config.selection_policy.lower()}"

        result = ProviderSelectionResult(
            provider_type=selected.type,
            provider_name=selected.name,
            selection_reason=reason,
            confidence=1.0,
            alternatives=[p.name for p in active_providers if p.name != selected.name],
        )

        if logger:
            logger.info("Selected active provider: %s (%s)", selected.name, reason)

        return result

    # ------------------------------------------------------------------
    # Internal selection strategies
    # ------------------------------------------------------------------

    def _select_by_cli_override(
        self, template: Any, provider_name: str, logger: Optional[Any]
    ) -> ProviderSelectionResult:
        """Select CLI-overridden provider with validation."""
        provider_instance = self._get_provider_instance_config(provider_name)
        if not provider_instance:
            raise ValueError(f"Provider instance '{provider_name}' not found")
        if not provider_instance.enabled:
            raise ValueError(f"Provider instance '{provider_name}' is disabled")

        return ProviderSelectionResult(
            provider_type=provider_instance.type,
            provider_name=provider_name,
            selection_reason=f"CLI name override (--provider-name {provider_name})",
            confidence=1.0,
        )

    def _select_by_explicit_provider(
        self, template: Any, logger: Optional[Any]
    ) -> ProviderSelectionResult:
        """Select explicitly specified provider instance."""
        provider_name = template.provider_name
        provider_instance = self._get_provider_instance_config(provider_name)
        if not provider_instance:
            raise ValueError(f"Provider instance '{provider_name}' not found in configuration")
        if not provider_instance.enabled:
            raise ValueError(f"Provider instance '{provider_name}' is disabled")

        if logger:
            logger.info("Selected explicit provider: %s", provider_name)

        return ProviderSelectionResult(
            provider_type=provider_instance.type,
            provider_name=provider_name,
            selection_reason="Explicitly specified in template",
            confidence=1.0,
        )

    def _select_by_provider_type(
        self, template: Any, logger: Optional[Any]
    ) -> ProviderSelectionResult:
        """Select provider instance using load balancing within provider type."""
        provider_type = template.provider_type
        instances = self._get_enabled_instances_by_type(provider_type)
        if not instances:
            raise ValueError(f"No enabled instances found for provider type '{provider_type}'")

        selected_instance = self._apply_load_balancing_strategy(instances)

        if logger:
            logger.info(
                "Selected load-balanced provider: %s (type: %s)",
                selected_instance.name,
                provider_type,
            )

        return ProviderSelectionResult(
            provider_type=provider_type,
            provider_name=selected_instance.name,
            selection_reason=f"Load balanced across {len(instances)} {provider_type} instances",
            confidence=0.9,
            alternatives=[inst.name for inst in instances if inst.name != selected_instance.name],
        )

    def _select_by_api_capability(
        self, template: Any, logger: Optional[Any]
    ) -> ProviderSelectionResult:
        """Select provider based on API capability support."""
        provider_api = template.provider_api
        compatible_instances = self._find_compatible_providers(provider_api)
        if not compatible_instances:
            raise ValueError(f"No providers support API '{provider_api}'")

        selected_instance = self._select_best_compatible_instance(compatible_instances)

        if logger:
            logger.info(
                "Selected capability-based provider: %s for API: %s",
                selected_instance.name,
                provider_api,
            )

        return ProviderSelectionResult(
            provider_type=selected_instance.type,
            provider_name=selected_instance.name,
            selection_reason=f"Supports required API '{provider_api}'",
            confidence=0.8,
            alternatives=[
                inst.name for inst in compatible_instances if inst.name != selected_instance.name
            ],
        )

    def _select_default_provider(
        self, template: Any, logger: Optional[Any]
    ) -> ProviderSelectionResult:
        """Select default provider from configuration."""
        provider_config = self._get_provider_config()
        if not provider_config:
            fallback = self._registry.get_fallback_strategy()
            if fallback is not None:
                if logger:
                    logger.info("No provider configuration available, using fallback strategy")
                return fallback
            raise ValueError("No provider configuration available")

        default_provider_type: Optional[str] = getattr(
            provider_config, "default_provider_type", None
        )
        default_provider_instance: Optional[str] = getattr(
            provider_config, "default_provider_instance", None
        )

        if not default_provider_instance:
            enabled_instances = [p for p in provider_config.providers if p.enabled]
            if not enabled_instances:
                raise ValueError("No enabled providers found in configuration")

            default_instance = enabled_instances[0]
            default_provider_type = default_instance.type
            default_provider_instance = default_instance.name

        if logger:
            logger.info("Selected default provider: %s", default_provider_instance)

        return ProviderSelectionResult(
            provider_type=default_provider_type or "",
            provider_name=default_provider_instance or "",
            selection_reason="Configuration default (no provider specified in template)",
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Load-balancing helpers
    # ------------------------------------------------------------------

    def _apply_load_balancing_strategy(
        self, instances: list[Any], selection_policy: Optional[str] = None
    ) -> Any:
        """Apply load balancing strategy to select instance."""
        provider_config = self._get_provider_config()
        if not selection_policy and provider_config:
            selection_policy = provider_config.selection_policy

        if selection_policy == "WEIGHTED_ROUND_ROBIN":
            return self._weighted_round_robin_selection(instances)
        elif selection_policy == "HEALTH_BASED":
            return self._health_based_selection(instances)
        elif selection_policy == "FIRST_AVAILABLE":
            return instances[0]
        else:
            return min(instances, key=lambda x: x.priority)

    def _weighted_round_robin_selection(self, instances: list[Any]) -> Any:
        """Select instance using priority-first, then weighted selection."""
        sorted_instances = sorted(instances, key=lambda x: x.priority)
        highest_priority = sorted_instances[0].priority
        highest_priority_instances = [
            instance for instance in sorted_instances if instance.priority == highest_priority
        ]

        if len(highest_priority_instances) == 1:
            selected = highest_priority_instances[0]
            self._logger.debug(
                "Selected provider %s (priority %s, weight %s)",
                selected.name,
                selected.priority,
                selected.weight,
            )
            return selected

        selected = max(highest_priority_instances, key=lambda x: x.weight)
        self._logger.debug(
            "Selected provider %s (priority %s, weight %s) from %s candidates",
            selected.name,
            selected.priority,
            selected.weight,
            len(highest_priority_instances),
        )
        return selected

    def _health_based_selection(self, instances: list[Any]) -> Any:
        """Select instance based on health status."""
        return min(instances, key=lambda x: x.priority)

    # ------------------------------------------------------------------
    # API-compatibility helpers
    # ------------------------------------------------------------------

    def _find_compatible_providers(self, provider_api: str) -> list[Any]:
        """Find provider instances that support the specified API."""
        provider_config = self._get_provider_config()
        if not provider_config:
            return []

        compatible = []
        for provider in provider_config.providers:
            if not provider.enabled:
                continue
            if self._provider_supports_api(provider, provider_api):
                compatible.append(provider)
        return compatible

    def _provider_supports_api(self, provider: Any, api: str) -> bool:
        """Check if provider instance supports the specified API."""
        provider_config = self._get_provider_config()
        if not provider_config:
            return False
        provider_defaults = provider_config.provider_defaults.get(provider.type)
        effective_handlers = provider.get_effective_handlers(provider_defaults)

        if not isinstance(effective_handlers, dict):
            effective_handlers = {}

        if api in effective_handlers:
            return True

        if provider.capabilities and api in provider.capabilities:
            return True

        strategy = self._registry.get_strategy(provider.name)
        if strategy is not None and hasattr(strategy, "get_capabilities"):
            try:
                caps = strategy.get_capabilities()
                if caps.supported_apis:
                    return api in caps.supported_apis
            except Exception as exc:
                self._logger.warning(
                    "Failed to check capabilities for API '%s': %s",
                    api,
                    exc,
                )

        return True

    def _select_best_compatible_instance(self, instances: list[Any]) -> Any:
        """Select the best instance from compatible providers."""
        return min(instances, key=lambda x: x.priority)

    def _provider_supports_capabilities(self, strategy: Any, capabilities: List[str]) -> bool:
        """Check if provider strategy supports required capabilities."""
        if not capabilities:
            return True

        provider_capabilities = getattr(strategy, "supported_capabilities", [])
        return all(cap in provider_capabilities for cap in capabilities)

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _get_cli_override(self) -> Optional[str]:
        """Get CLI provider override from configuration."""
        return None  # CLI override handled at higher level

    def _get_provider_config(self) -> Optional[Any]:
        """Get provider configuration via the injected configuration port."""
        try:
            if self._config_port:
                return self._config_port.get_provider_config()
        except Exception as e:
            self._logger.debug("Failed to get provider configuration: %s", e)
        return None

    def _get_provider_instance_config(self, provider_name: str) -> Optional[Any]:
        """Get provider instance configuration by name."""
        provider_config = self._get_provider_config()
        if not provider_config:
            return None
        for provider in provider_config.providers:
            if provider.name == provider_name:
                return provider
        return None

    def _get_enabled_instances_by_type(self, provider_type: str) -> list[Any]:
        """Get all enabled provider instances of specified type."""
        provider_config = self._get_provider_config()
        if not provider_config:
            return []
        return [
            provider
            for provider in provider_config.providers
            if provider.type == provider_type and provider.enabled
        ]
