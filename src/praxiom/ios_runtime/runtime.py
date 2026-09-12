"""Public six-operation Native iOS Runtime v0 (R3-05).

Integrates the R3-02 transport, the R3-03 observation/revision engine, and the
R3-04 executor behind the R2 contract's exact public surface (sections 4-6):

- ``status()`` — side-effect-free health/limits projection; privacy-safe by
  construction (state enums, counters, opaque tokens only — never device
  identifiers, pair records, screen text, or action payloads);
- ``observe()`` — connects the owned plumbing and captures one
  ``Observation`` plus a fresh opaque revision through ``ObservationEngine``;
- ``execute()`` — delegates whole-batch preflight and ordered execution to the
  ``ActionExecutor``. A no-effect preflight rejection (empty/over-limit batch,
  validation failure, stale revision, foreign element ref) makes zero device
  calls and leaves the revision intact. Any attempted mutation invalidates the
  accepted revision whether the batch succeeds or fails. A connection-class
  failure or timeout after a request was sent surfaces as ``EFFECT_UNKNOWN``
  and is never automatically replayed; a definitive failure is
  ``ACTION_FAILED`` (``PARTIAL`` where knowable) — both ``retry_safe=False``;
- ``invalidate(reason)`` — local revision invalidation only, never a device
  call; the machine-oriented reason is bounded
  (``INVALIDATE_REASON_MAX_LENGTH``). Traceability retains only a
  Runtime-local keyed fingerprint, never the raw reason;
- ``recover()`` — rebuilds device plumbing exclusively via the transport's
  ``recreate()`` (it knows nothing about actions, so it can never replay one)
  and always invalidates the pre-recovery revision;
- ``close()`` — idempotent teardown of exactly the resources this Runtime
  owns; afterwards ``observe``/``execute``/``recover`` raise
  ``RUNTIME_CLOSED`` while ``status()`` stays callable and reports CLOSED;
- ``trace`` — R3-06 observability attribute (see ``trace.py``): per-operation
  latency records and machine-readable operation/error counters, privacy-safe
  by construction. State projection only, not one of the six operations.

Operations are serialized on one asyncio lock (the transport runs its
operation primitives lock-free against a single owned WDA session);
``status()`` reads snapshots without the lock.
"""

import asyncio
import hashlib
import secrets
from collections.abc import Callable, Sequence
from typing import Any

from praxiom.ios_runtime.executor import ActionExecutor
from praxiom.ios_runtime.models import (
    Action,
    Element,
    ErrorCode,
    ErrorEffect,
    ErrorPhase,
    ExecutionResult,
    ObserveRequest,
    Observation,
    RecoveryResult,
    RuntimeLimits,
    RuntimeOperationError,
    RuntimeStatus,
    ScreenSize,
)
from praxiom.ios_runtime.observation import ObservationEngine
from praxiom.ios_runtime.trace import Trace
from praxiom.ios_runtime.transport import IosTransport, TransportError

__all__ = ["NativeIosRuntime"]

CONTRACT_VERSION = "v0"
_DEFAULT_MAX_BATCH_ACTIONS = 32

# R2 contract 4.4: the invalidate reason is machine-oriented and bounded for
# traceability. The bound is enforced before any side effect (an over-limit
# or non-machine-oriented reason is rejected with INVALID_REQUEST and leaves
# the current revision intact). The raw reason is never retained in trace;
# only a Runtime-local keyed fingerprint is recorded as invalidate detail.
INVALIDATE_REASON_MAX_LENGTH = 128

# Static v0 capability projection (contract 4.1): capability names only.
_CAPABILITIES = {
    "actions": (
        "tap_point",
        "tap_element",
        "drag",
        "swipe",
        "type_text",
        "home",
        "launch_app",
    ),
    "sources": ("screenshot", "accessibility"),
}


def _no_effect(
    code: ErrorCode, phase: ErrorPhase = ErrorPhase.LIFECYCLE
) -> RuntimeOperationError:
    """No-effect failure: nothing was sent to the device (contract 5.1)."""
    return RuntimeOperationError(code, phase, ErrorEffect.NONE, retry_safe=True)


def _check_invalidate_reason(reason: str) -> str:
    """Validate the machine-oriented bounded invalidate reason (contract 4.4).

    Returns the reason unchanged when it is a non-blank ASCII-printable
    string within ``INVALIDATE_REASON_MAX_LENGTH``; otherwise raises a
    no-effect ``INVALID_REQUEST`` preflight error before any state changes.
    """
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > INVALIDATE_REASON_MAX_LENGTH
        or not (reason.isascii() and reason.isprintable())
    ):
        raise _no_effect(ErrorCode.INVALID_REQUEST, ErrorPhase.PREFLIGHT)
    return reason


class _RevisionView:
    """Executor-facing read-only view of the runtime's current revision.

    Adapts the ObservationEngine's raise-on-miss lookups to the executor's
    fail-closed ``RevisionRegistry`` protocol (unknown revision/ref -> None).
    Every lookup is in-memory, so preflight costs zero device calls, and refs
    from any other revision fail closed exactly like unknown refs (R2-A09).
    """

    def __init__(self, runtime: "NativeIosRuntime") -> None:
        self._runtime = runtime

    def current_revision(self) -> str | None:
        return self._runtime._engine.current_revision

    def screen_size(self, revision: str) -> ScreenSize | None:
        observation = self._runtime._observation
        if revision == self.current_revision() and observation is not None:
            return observation.screen
        return None

    def logical_screen_size(self, revision: str) -> tuple[int, int] | None:
        try:
            return self._runtime._engine.logical_screen(revision)
        except RuntimeOperationError:
            return None

    def element(self, revision: str, ref: str) -> Element | None:
        if revision != self.current_revision():
            return None
        return self._runtime._elements.get(ref)


class NativeIosRuntime:
    """The R2 public contract: exactly six async operations.

    ``transport`` defaults to a real upstream-backed ``IosTransport``;
    deterministic tests inject a fake with the same operation surface.
    """

    def __init__(
        self,
        transport: Any = None,
        *,
        max_batch_actions: int = _DEFAULT_MAX_BATCH_ACTIONS,
        xctrunner_bundle_id: str | None = None,
        frame_sink: Callable[[bytes, Observation], None] | None = None,
    ) -> None:
        if (
            not isinstance(max_batch_actions, int)
            or isinstance(max_batch_actions, bool)
            or max_batch_actions < 1
        ):
            raise ValueError("max_batch_actions must be a positive integer")
        self._transport = (
            transport
            if transport is not None
            else IosTransport(xctrunner_bundle_id=xctrunner_bundle_id)
        )
        self._engine = ObservationEngine(self._transport, frame_sink=frame_sink)
        self._executor = ActionExecutor(
            self._transport, _RevisionView(self), max_batch_actions=max_batch_actions
        )
        self._max_batch_actions = max_batch_actions
        self._observation: Observation | None = None
        self._elements: dict[str, Element] = {}
        self._last_error_code: ErrorCode | None = None
        self._closed = False
        self._op_lock = asyncio.Lock()
        self._trace_reason_key = secrets.token_bytes(16)
        # R3-06 observability: latency records + lifecycle/error counters.
        self.trace = Trace()

    # --- the six public operations ------------------------------------------

    async def status(self) -> RuntimeStatus:
        """Side-effect-free health/limits snapshot (contract 4.1)."""
        snapshot = self._transport.snapshot()
        return RuntimeStatus(
            contract_version=CONTRACT_VERSION,
            lifecycle_state=snapshot.lifecycle,
            transport=snapshot.transport,
            wda_state=snapshot.wda_state,
            current_revision=self._engine.current_revision,
            capabilities=dict(_CAPABILITIES),
            limits=RuntimeLimits(max_batch_actions=self._max_batch_actions),
            last_error_code=self._last_error_code,
        )

    async def observe(self, request: ObserveRequest | None = None) -> Observation:
        """Capture one observation and install a fresh current revision."""
        async with self._op_lock:
            started = self.trace.start()
            self._require_open()
            try:
                await self._transport.connect()
                observation = await self._engine.capture(request)
            except TransportError:
                self._last_error_code = ErrorCode.OBSERVATION_FAILED
                self.trace.record(
                    "observe",
                    started=started,
                    error_code=ErrorCode.OBSERVATION_FAILED,
                )
                raise _no_effect(ErrorCode.OBSERVATION_FAILED) from None
            except RuntimeOperationError as exc:
                self._last_error_code = exc.code
                self.trace.record("observe", started=started, error_code=exc.code)
                raise
            self._observation = observation
            self._elements = {el.ref: el for el in observation.elements}
            self._last_error_code = None
            self.trace.record("observe", started=started)
            return observation

    async def execute(
        self, actions: Sequence[Action], *, expected_revision: str
    ) -> ExecutionResult:
        """Validate the whole batch, then execute it in order (contract 4.3)."""
        async with self._op_lock:
            started = self.trace.start()
            self._require_open()
            try:
                result = await self._executor.execute(
                    actions, expected_revision=expected_revision
                )
            except RuntimeOperationError as exc:
                self._last_error_code = exc.code
                self.trace.record(
                    "execute",
                    started=started,
                    error_code=exc.code,
                    failed_action_index=exc.failed_action_index,
                )
                if exc.revision_invalidated:
                    self._forget_revision()
                raise
            if result.accepted_revision_invalidated:
                self._forget_revision()
            self._last_error_code = None
            self.trace.record("execute", started=started, outcomes=result.outcomes)
            return result

    async def invalidate(self, reason: str) -> None:
        """Local-only invalidation; never sends a device action (contract 4.4).

        Still usable after close (close already invalidated the revision), so
        the operation is a harmless no-op there.
        """
        # The raw reason is never trace-safe by assumption. Preserve only a
        # runtime-local keyed fingerprint for correlation/traceability.
        validated = _check_invalidate_reason(reason)
        detail = "reason#" + hashlib.blake2s(
            validated.encode("ascii"),
            key=self._trace_reason_key,
            digest_size=8,
        ).hexdigest()
        async with self._op_lock:
            started = self.trace.start()
            self._forget_revision()
            self.trace.record("invalidate", started=started, detail=detail)

    async def recover(self) -> RecoveryResult:
        """Rebuild plumbing only; never replays actions (contract 4.5)."""
        async with self._op_lock:
            started = self.trace.start()
            self._require_open()
            # Always invalidated, even when the rebuild itself fails.
            self._forget_revision()
            try:
                await self._transport.recreate()
            except TransportError:
                self._last_error_code = ErrorCode.RECOVERY_FAILED
                self.trace.record(
                    "recover",
                    started=started,
                    error_code=ErrorCode.RECOVERY_FAILED,
                )
                raise _no_effect(ErrorCode.RECOVERY_FAILED) from None
            self._last_error_code = None
            self.trace.record("recover", started=started)
            return RecoveryResult(repaired=True)

    async def close(self) -> None:
        """Idempotently release exactly the resources this Runtime owns."""
        async with self._op_lock:
            if self._closed:
                return
            self._closed = True
            self._forget_revision()  # close invalidates the revision (contract 6)
            await self._transport.close()

    # --- internal -------------------------------------------------------------

    def _require_open(self) -> None:
        if self._closed:
            self._last_error_code = ErrorCode.RUNTIME_CLOSED
            raise _no_effect(ErrorCode.RUNTIME_CLOSED)

    def _forget_revision(self) -> None:
        self._engine.invalidate()
        self._observation = None
        self._elements = {}
