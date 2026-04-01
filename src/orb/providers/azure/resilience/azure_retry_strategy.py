"""Azure-specific retry strategy.

Determines whether an Azure SDK exception is retryable and calculates
backoff delays with jitter.
"""

import secrets
from typing import Optional

from orb.domain.base.dependency_injection import injectable
from orb.domain.base.ports import LoggingPort
from orb.infrastructure.resilience.strategy.base import RetryStrategy


# Azure error codes that are generally safe to retry.
# See: https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/common-deployment-errors
_RETRYABLE_ERROR_CODES: frozenset[str] = frozenset({
    # HTTP-level transients
    "429",  # TooManyRequests / throttling
    "500",  # InternalServerError
    "502",  # BadGateway
    "503",  # ServiceUnavailable
    "504",  # GatewayTimeout

    # ARM / SDK error codes
    "RetryableError",
    "Throttled",
    "TooManyRequests",
    "ServerBusy",
    "InternalServerError",
    "ServiceUnavailable",
    "OperationNotAllowed",  # sometimes transient during ARM propagation
    "ConflictError",  # occasionally transient during resource creation
    "DeploymentActive",  # another deployment is in progress
})


def is_retryable_azure_error(exception: Exception) -> bool:
    """Return ``True`` if the exception is a retryable Azure SDK error.

    Uses getattr because the function accepts any Exception and probes for
    attributes that only some azure-core subclasses carry (status_code,
    error_code, error, error.code).
    """
    status_code = getattr(exception, "status_code", None)
    if status_code is not None and str(status_code) in _RETRYABLE_ERROR_CODES:
        return True

    error_code = getattr(exception, "error_code", None) or ""
    if error_code in _RETRYABLE_ERROR_CODES:
        return True

    error = getattr(exception, "error", None)
    if error:
        code = getattr(error, "code", None) or ""
        if code in _RETRYABLE_ERROR_CODES:
            return True

    # Check string representation as last resort
    exc_str = str(exception).lower()
    if any(keyword in exc_str for keyword in ("throttl", "too many requests", "service unavailable")):
        return True

    return False


@injectable
class AzureRetryStrategy(RetryStrategy):
    """Azure-specific retry strategy with ARM-aware error handling."""

    def __init__(
        self,
        logger: LoggingPort,
        service: str = "compute",
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ) -> None:
        self._logger = logger
        self.service = service
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def should_retry(self, attempt: int, exception: Exception) -> bool:
        """Determine if the given exception is retryable based on Azure SDK error patterns and number of retries."""
        if attempt >= self.max_attempts:
            return False
        return is_retryable_azure_error(exception)

    def get_delay(self, attempt: int) -> float:
        """Gets the delay before the next retry attempt, using exponential backoff with optional jitter."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            rng = secrets.SystemRandom()
            jitter_amount = delay * 0.1 * (rng.random() * 2 - 1)
            delay = max(0.0, delay + jitter_amount)
        return delay

    def on_retry(self, attempt: int, exception: Exception) -> None:
        """Log a warning about the retry attempt and the exception that caused it."""
        self._logger.warning(
            "Retrying Azure %s operation (attempt %d/%d) after error: %s",
            self.service,
            attempt + 1,
            self.max_attempts,
            exception,
        )
