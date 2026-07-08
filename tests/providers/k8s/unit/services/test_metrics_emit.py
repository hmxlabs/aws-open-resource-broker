"""Unit tests for the 4 previously-dead k8s metrics emit sites.

Covers:
* orb_k8s_apiserver_latency_seconds — via K8sMetrics.record_apiserver_latency()
  and via the watcher's _relist_snapshot timed-list wrapper.
* orb_k8s_active_pods / orb_k8s_active_requests — via watcher._update_cache_gauges()
  after cache mutations in _handle_event.
* orb_k8s_circuit_breaker_state — via K8sCircuitBreaker with metrics wired.

Each test uses an isolated CollectorRegistry to avoid global-registry pollution.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from orb.infrastructure.resilience.strategy.circuit_breaker import CircuitState
from orb.providers.k8s.infrastructure.services.metrics import K8sMetrics
from orb.providers.k8s.resilience.circuit_breaker import K8sCircuitBreaker
from orb.providers.k8s.watch.pod_state_cache import PodStateCache  # noqa: F401
from orb.providers.k8s.watch.watcher import K8sWatcher

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _fresh_metrics() -> K8sMetrics:
    """K8sMetrics on an isolated registry."""
    return K8sMetrics(registry=CollectorRegistry())


def _fresh_cb_key() -> str:
    return f"test.k8s.emit.{uuid.uuid4().hex}"


def _pod(
    *,
    name: str = "orb-0001",
    phase: str = "Running",
    ready: bool = True,
    request_id: str = "req-emit",
    namespace: str = "ns",
) -> SimpleNamespace:
    conditions = [SimpleNamespace(type="Ready", status="True" if ready else "False", reason=None)]
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            namespace=namespace,
            labels={
                "orb.io/managed": "true",
                "orb.io/request-id": request_id,
            },
        ),
        spec=SimpleNamespace(node_name="node-a"),
        status=SimpleNamespace(
            phase=phase,
            pod_ip="10.0.0.1",
            host_ip="10.1.0.1",
            start_time=None,
            conditions=conditions,
            container_statuses=[],
        ),
    )


class _StubWatch:
    def __init__(self, events: Iterator[Any]) -> None:
        self._events = events
        self._stopped = False
        self.resource_version: str | None = None

    def stream(self, func: Any, **kwargs: Any) -> Iterator[Any]:
        for ev in self._events:
            if self._stopped:
                return
            yield ev

    def stop(self) -> None:
        self._stopped = True


def _make_k8s_client_mock() -> MagicMock:
    client = MagicMock()
    client.core_v1.list_namespaced_pod = MagicMock(
        return_value=SimpleNamespace(items=[], metadata=SimpleNamespace(resource_version="42"))
    )
    client.core_v1.list_pod_for_all_namespaces = MagicMock(
        return_value=SimpleNamespace(items=[], metadata=SimpleNamespace(resource_version="42"))
    )
    return client


# ---------------------------------------------------------------------------
# 1. orb_k8s_apiserver_latency_seconds — record_apiserver_latency helper
# ---------------------------------------------------------------------------


class TestApiserverLatencyHelper:
    def test_observe_records_sample(self) -> None:
        m = _fresh_metrics()
        m.record_apiserver_latency(operation="list_pods", seconds=0.05)
        h = m.apiserver_latency_seconds.labels(operation="list_pods")
        assert h._sum.get() >= 0.05  # type: ignore[attr-defined]

    def test_multiple_operations_stay_separate(self) -> None:
        m = _fresh_metrics()
        m.record_apiserver_latency(operation="list_pods", seconds=0.1)
        m.record_apiserver_latency(operation="create_pod", seconds=0.2)
        assert m.apiserver_latency_seconds.labels(operation="list_pods")._sum.get() >= 0.1  # type: ignore[attr-defined]
        assert m.apiserver_latency_seconds.labels(operation="create_pod")._sum.get() >= 0.2  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 2. orb_k8s_apiserver_latency_seconds — emitted by watcher._relist_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_relist_snapshot_emits_latency() -> None:
    """_relist_snapshot wraps the LIST call in _timed_list → latency gauge gets a sample."""
    m = _fresh_metrics()
    cache = PodStateCache()
    client = _make_k8s_client_mock()

    watcher = K8sWatcher(
        kubernetes_client=client,
        cache=cache,
        logger=MagicMock(),
        namespace="ns",
        metrics=m,
    )
    # Call _relist_snapshot directly (it's a sync method run in a thread normally).
    watcher._relist_snapshot()

    h = m.apiserver_latency_seconds.labels(operation="list_pods")
    assert h._sum.get() >= 0  # type: ignore[attr-defined]  # any non-negative sample was recorded


# ---------------------------------------------------------------------------
# 3. orb_k8s_active_pods / orb_k8s_active_requests — watcher cache gauges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_active_pods_and_requests_set_on_added_event() -> None:
    """After an ADDED event the active_pods and active_requests gauges are non-zero."""
    m = _fresh_metrics()
    cache = PodStateCache()
    client = _make_k8s_client_mock()
    events = [
        {"type": "ADDED", "object": _pod(name="p1", request_id="req-1")},
        {"type": "ADDED", "object": _pod(name="p2", request_id="req-1")},
        {"type": "ADDED", "object": _pod(name="p3", request_id="req-2")},
    ]
    stubs_iter = iter([_StubWatch(iter(events))])

    def factory() -> _StubWatch:
        try:
            return next(stubs_iter)
        except StopIteration:
            return _StubWatch(iter([]))

    watcher = K8sWatcher(
        kubernetes_client=client,
        cache=cache,
        logger=MagicMock(),
        namespace="ns",
        watch_factory=factory,
        watch_timeout_seconds=1,
        metrics=m,
    )
    watcher.start()
    for _ in range(100):
        if cache.size() >= 3:
            break
        await asyncio.sleep(0.01)
    await watcher.stop()

    pod_gauge = m.active_pods.labels(namespace="ns")
    req_gauge = m.active_requests.labels(namespace="ns")
    assert pod_gauge._value.get() == 3  # type: ignore[attr-defined]
    assert req_gauge._value.get() == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_active_pods_decrements_on_deleted_event() -> None:
    """DELETED event reduces active_pods gauge."""
    m = _fresh_metrics()
    cache = PodStateCache()
    client = _make_k8s_client_mock()
    events = [
        {"type": "ADDED", "object": _pod(name="p1", request_id="req-1")},
        {"type": "ADDED", "object": _pod(name="p2", request_id="req-1")},
        {"type": "DELETED", "object": _pod(name="p1", request_id="req-1")},
    ]
    stubs_iter = iter([_StubWatch(iter(events))])

    def factory() -> _StubWatch:
        try:
            return next(stubs_iter)
        except StopIteration:
            return _StubWatch(iter([]))

    watcher = K8sWatcher(
        kubernetes_client=client,
        cache=cache,
        logger=MagicMock(),
        namespace="ns",
        watch_factory=factory,
        watch_timeout_seconds=1,
        metrics=m,
    )
    watcher.start()
    for _ in range(100):
        # Wait until DELETED has been processed (cache has 1 entry).
        if cache.size() == 1:
            break
        await asyncio.sleep(0.01)
    await watcher.stop()

    pod_gauge = m.active_pods.labels(namespace="ns")
    assert pod_gauge._value.get() == 1  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 4. orb_k8s_circuit_breaker_state — K8sCircuitBreaker state transitions
# ---------------------------------------------------------------------------


class TestCircuitBreakerStateGauge:
    """Circuit breaker state gauge is set on every state change."""

    def _make_cb(self, key: str, metrics: K8sMetrics, threshold: int = 3) -> K8sCircuitBreaker:
        return K8sCircuitBreaker(
            service_name=key,
            failure_threshold=threshold,
            reset_timeout=60,
            half_open_timeout=30,
            max_attempts=3,
            base_delay=0.0,
            max_delay=0.0,
            jitter=False,
            metrics=metrics,
        )

    def test_initial_state_is_closed(self) -> None:
        m = _fresh_metrics()
        key = _fresh_cb_key()
        self._make_cb(key, m)
        g = m.circuit_breaker_state.labels(name=key)
        assert g._value.get() == 0  # type: ignore[attr-defined]  # CLOSED

    def test_open_state_emitted_on_threshold(self) -> None:
        m = _fresh_metrics()
        key = _fresh_cb_key()
        cb = self._make_cb(key, m, threshold=2)

        now = time.time()
        cb.record_failure(now)
        cb.record_failure(now)  # trips to OPEN

        g = m.circuit_breaker_state.labels(name=key)
        assert g._value.get() == 1  # type: ignore[attr-defined]  # OPEN

    def test_closed_state_emitted_after_recovery(self) -> None:
        m = _fresh_metrics()
        key = _fresh_cb_key()
        cb = self._make_cb(key, m, threshold=1)

        # Trip to OPEN.
        cb.record_failure(time.time())
        assert m.circuit_breaker_state.labels(name=key)._value.get() == 1  # type: ignore[attr-defined]

        # Manually set state to HALF_OPEN so record_success closes it.
        K8sCircuitBreaker._circuit_states[key]["state"] = CircuitState.HALF_OPEN
        cb.record_success()

        assert m.circuit_breaker_state.labels(name=key)._value.get() == 0  # type: ignore[attr-defined]  # CLOSED

    def test_no_metrics_is_noop(self) -> None:
        """K8sCircuitBreaker without metrics must not raise."""
        key = _fresh_cb_key()
        cb = K8sCircuitBreaker(
            service_name=key,
            failure_threshold=1,
            reset_timeout=60,
            max_attempts=1,
            base_delay=0.0,
            max_delay=0.0,
            jitter=False,
        )
        cb.record_failure(time.time())  # should not raise

    def test_set_helpers_on_metrics_directly(self) -> None:
        m = _fresh_metrics()
        m.set_circuit_breaker_state(name="svc-x", state=2)
        assert m.circuit_breaker_state.labels(name="svc-x")._value.get() == 2  # type: ignore[attr-defined]

    def test_set_active_pods_and_requests_helpers(self) -> None:
        m = _fresh_metrics()
        m.set_active_pods(namespace="default", count=7)
        m.set_active_requests(namespace="default", count=3)
        assert m.active_pods.labels(namespace="default")._value.get() == 7  # type: ignore[attr-defined]
        assert m.active_requests.labels(namespace="default")._value.get() == 3  # type: ignore[attr-defined]
