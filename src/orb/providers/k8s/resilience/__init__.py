"""K8s-specific resilience components."""

from orb.providers.k8s.resilience.circuit_breaker import K8sCircuitBreaker

__all__ = ["K8sCircuitBreaker"]
