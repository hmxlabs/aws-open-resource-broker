"""K8s-specific retry classifier.

Flags Kubernetes ApiException instances whose HTTP status code represents
a permanent client error (4xx). These must not consume retry budget or
count as circuit-breaker failures — they surface immediately.
"""

from __future__ import annotations

_NON_RETRYABLE_STATUSES: frozenset[int] = frozenset({400, 403, 404, 409, 410, 422})


class K8sRetryClassifier:
    """Retry classifier for the Kubernetes SDK's ApiException."""

    def is_non_retryable(self, exception: Exception) -> bool:
        try:
            from kubernetes.client.exceptions import ApiException  # noqa: PLC0415
        except ImportError:
            return False

        if not isinstance(exception, ApiException):
            return False
        status = getattr(exception, "status", None)
        return status in _NON_RETRYABLE_STATUSES
