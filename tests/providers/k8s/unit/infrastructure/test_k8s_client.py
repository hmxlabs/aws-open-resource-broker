"""Unit tests for :class:`K8sClient` — token refresh and cleanup behaviour."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from orb.providers.k8s.configuration.config import K8sProviderConfig


def _make_client(api_client: object | None = None) -> "K8sClient":
    from orb.providers.k8s.infrastructure.k8s_client import K8sClient

    mock_logger = MagicMock()
    cfg = K8sProviderConfig()
    return K8sClient(config=cfg, logger=mock_logger, api_client=api_client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cleanup() calls api_client.close()
# ---------------------------------------------------------------------------


def test_cleanup_calls_api_client_close() -> None:
    """cleanup() must call close() on the underlying ApiClient."""
    mock_api_client = MagicMock()
    client = _make_client(api_client=mock_api_client)

    client.cleanup()

    mock_api_client.close.assert_called_once()


def test_cleanup_idempotent() -> None:
    """Calling cleanup() twice must not raise and must call close() only once."""
    mock_api_client = MagicMock()
    client = _make_client(api_client=mock_api_client)

    client.cleanup()
    client.cleanup()  # second call — api_client is now None

    mock_api_client.close.assert_called_once()


def test_cleanup_tolerates_missing_close() -> None:
    """cleanup() must not raise when ApiClient has no close() method."""
    mock_api_client = object()  # no close attribute
    client = _make_client(api_client=mock_api_client)
    client.cleanup()  # must not raise


# ---------------------------------------------------------------------------
# call_with_auth_retry — 401 triggers one retry
# ---------------------------------------------------------------------------


def test_call_with_auth_retry_succeeds_first_time() -> None:
    """call_with_auth_retry passes through when fn succeeds on the first call."""
    mock_api_client = MagicMock()
    client = _make_client(api_client=mock_api_client)

    fn = MagicMock(return_value="ok")
    result = client.call_with_auth_retry(fn, "arg1", key="val")

    fn.assert_called_once_with("arg1", key="val")
    assert result == "ok"


def test_call_with_auth_retry_retries_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 ApiException must cause one retry after credential refresh."""
    import sys

    class _FakeApiException(Exception):
        def __init__(self, status: int) -> None:
            self.status = status
            super().__init__(f"HTTP {status}")

    fake_exceptions = SimpleNamespace(ApiException=_FakeApiException)
    monkeypatch.setitem(sys.modules, "kubernetes.client.exceptions", fake_exceptions)

    mock_api_client = MagicMock()
    client = _make_client(api_client=mock_api_client)
    # Wire a fake in-cluster adapter so the refresh path is exercised.
    mock_adapter = MagicMock()
    mock_adapter.refresh_if_stale.return_value = False
    client._in_cluster_adapter = mock_adapter  # noqa: SLF001

    # fn fails first with 401, then succeeds.
    fn = MagicMock(side_effect=[_FakeApiException(401), "recovered"])

    with patch(
        "orb.providers.k8s.infrastructure.k8s_client.load_in_cluster_config"
    ) as mock_reload:
        result = client.call_with_auth_retry(fn)

    assert result == "recovered"
    assert fn.call_count == 2
    mock_reload.assert_called_once()


def test_call_with_auth_retry_does_not_retry_non_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-401 exceptions are not retried."""
    import sys

    class _FakeApiException(Exception):
        def __init__(self, status: int) -> None:
            self.status = status

    fake_exceptions = SimpleNamespace(ApiException=_FakeApiException)
    monkeypatch.setitem(sys.modules, "kubernetes.client.exceptions", fake_exceptions)

    mock_api_client = MagicMock()
    client = _make_client(api_client=mock_api_client)

    fn = MagicMock(side_effect=_FakeApiException(403))

    with pytest.raises(_FakeApiException):
        client.call_with_auth_retry(fn)

    fn.assert_called_once()


# ---------------------------------------------------------------------------
# refresh_if_stale proxies to InClusterAuthAdapter
# ---------------------------------------------------------------------------


def test_refresh_if_stale_noop_with_api_client_override() -> None:
    """refresh_if_stale() must return False when api_client was pre-supplied.

    When a pre-built ApiClient is injected (typical in unit tests) there is
    no in-cluster adapter and the method is a no-op.
    """
    mock_api_client = MagicMock()
    client = _make_client(api_client=mock_api_client)

    # adapter must be None when api_client was pre-supplied
    assert client._in_cluster_adapter is None  # noqa: SLF001
    assert client.refresh_if_stale() is False
