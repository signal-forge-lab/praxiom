"""R3-06 privacy-safe status/trace tests: R2-A01, latency records, counters.

Reuses the fault-injecting fake transport from test_runtime at the
runtime/transport boundary (no device required):

- R2-A01 — a READY runtime's status() exposes capabilities and the
  runtime-owned batch limit, and neither status() nor trace output exposes
  device identifiers, pair records, screen text, raw action payloads, or
  secrets: real operations carry UDID-shaped 40-hex/25-hex payloads, a secret
  fragment, and screen text, then both outputs are scanned;
- latency — observe / execute (batch duration + per-action outcomes) /
  recover records carry the durations needed for later latency comparison;
- counters — machine-readable operation and error-code counts.
"""

import dataclasses
import json
import re

import pytest

from praxiom.ios_runtime.models import (
    ErrorCode,
    Home,
    LifecycleState,
    RuntimeOperationError,
    TapPoint,
    TypeText,
)
from praxiom.ios_runtime.runtime import INVALIDATE_REASON_MAX_LENGTH
from praxiom.ios_runtime.transport import WdaUnreachableError
from test_runtime import make_runtime, run

# UDID-shaped payloads and a secret fragment pushed through real operations;
# neither status() nor trace output may contain any of them.
_UDID_40 = "0123456789abcdef0123456789abcdef01234567"
_UDID_25 = "0123456789abcdef01234"
_SECRET_PAYLOAD = f"{_UDID_40}-{_UDID_25}-p4ssw0rd!"
_HEX_40 = re.compile(r"\b[0-9a-fA-F]{40}\b")
_HEX_25 = re.compile(r"\b[0-9a-fA-F]{25}\b")
_FORBIDDEN = ("device_udid", "pair_record", "screen_text", "raw_action_payload")


def _assert_no_private_identifiers(text: str) -> None:
    lowered = text.lower()
    for forbidden in _FORBIDDEN:
        assert forbidden not in lowered, forbidden
    assert _HEX_40.search(text) is None, "40-hex UDID-like identifier in output"
    assert _HEX_25.search(text) is None, "25-hex UDID-like identifier in output"


# --- R2-A01 ---------------------------------------------------------------------


def test_r2_a01_ready_status_and_trace_are_privacy_safe():
    runtime, _ = make_runtime()
    observation = run(runtime.observe())
    run(
        runtime.execute(
            [TapPoint(x=10, y=20), TypeText(text=_SECRET_PAYLOAD)],
            expected_revision=observation.revision,
        )
    )

    status = run(runtime.status())
    # Fixture given/expect: READY, revision consumed by the executed batch,
    # capabilities and the runtime-owned batch limit advertised.
    assert status.lifecycle_state == LifecycleState.READY
    assert status.current_revision is None
    assert status.limits.max_batch_actions == 32
    assert "tap_point" in status.capabilities["actions"]
    assert "screenshot" in status.capabilities["sources"]

    status_text = json.dumps(dataclasses.asdict(status), default=str)
    trace_text = json.dumps(runtime.trace.render())
    for text in (status_text, trace_text):
        _assert_no_private_identifiers(text)
        assert _UDID_40 not in text  # the raw type_text payload never surfaces
        assert _UDID_25 not in text
        assert "p4ssw0rd!" not in text
    # Screen text (the fake accessibility label) and opaque revision/element
    # tokens never reach the trace.
    assert "Go" not in trace_text
    assert observation.revision not in trace_text
    assert all(element.ref not in trace_text for element in observation.elements)


# --- latency records -------------------------------------------------------------


def test_trace_records_observe_batch_action_and_recovery_latency():
    runtime, _ = make_runtime()
    first = run(runtime.observe())
    run(
        runtime.execute(
            [TapPoint(x=10, y=20), TypeText(text="abc")],
            expected_revision=first.revision,
        )
    )
    run(runtime.recover())
    run(runtime.observe())

    records = runtime.trace.records
    observe_records = [r for r in records if r.operation == "observe"]
    batch_records = [r for r in records if r.operation == "execute"]
    recover_records = [r for r in records if r.operation == "recover"]
    assert (len(observe_records), len(batch_records), len(recover_records)) == (2, 1, 1)
    for record in records:
        assert record.duration_ms >= 0.0
        assert record.error_code is None

    # Per-batch and per-action latency for the executed batch.
    (batch,) = batch_records
    assert [(o.index, o.kind) for o in batch.outcomes] == [
        (0, "tap_point"),
        (1, "type_text"),
    ]
    assert all(o.duration_ms >= 0.0 for o in batch.outcomes)
    # Recovery latency is its own record; it replayed nothing into it.
    (recovery,) = recover_records
    assert recovery.outcomes == ()


# --- counters --------------------------------------------------------------------


def test_trace_counters_count_operations_and_errors():
    runtime, transport = make_runtime(
        faults={1: TimeoutError()},
        connect_error=WdaUnreachableError("probe failed"),
    )
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.observe())
    assert err.value.code == ErrorCode.OBSERVATION_FAILED
    transport._connect_error = None
    observation = run(runtime.observe())
    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [TapPoint(x=10, y=20), Home()],
                expected_revision=observation.revision,
            )
        )
    assert err.value.code == ErrorCode.EFFECT_UNKNOWN
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute([Home()], expected_revision=observation.revision))
    assert err.value.code == ErrorCode.STALE_REVISION
    run(runtime.recover())

    assert dict(runtime.trace.operations) == {"observe": 2, "execute": 2, "recover": 1}
    assert dict(runtime.trace.errors) == {
        ErrorCode.OBSERVATION_FAILED: 1,
        ErrorCode.EFFECT_UNKNOWN: 1,
        ErrorCode.STALE_REVISION: 1,
    }
    rendered = runtime.trace.render()
    assert rendered["counters"]["operations"] == dict(runtime.trace.operations)
    assert rendered["counters"]["errors"] == {
        code.value: count for code, count in runtime.trace.errors.items()
    }
    # The ambiguous-failure batch record carries the failed action index.
    failed = [
        r
        for r in runtime.trace.records
        if r.operation == "execute" and r.error_code == ErrorCode.EFFECT_UNKNOWN
    ]
    assert len(failed) == 1
    assert failed[0].failed_action_index == 1


# --- invalidate traceability (R2 4.4) --------------------------------------------


def test_trace_invalidate_reason_is_fingerprinted_and_privacy_safe():
    runtime, _ = make_runtime()
    observation = run(runtime.observe())
    # Rejected reasons are never recorded: the trace cannot carry raw
    # user/device content smuggled through a hostile reason.
    for bad_reason in ("", "x" * (INVALIDATE_REASON_MAX_LENGTH + 1), "line1\nline2", _SECRET_PAYLOAD * 4):
        with pytest.raises(RuntimeOperationError):
            run(runtime.invalidate(bad_reason))
    assert [r for r in runtime.trace.records if r.operation == "invalidate"] == []
    assert "invalidate" not in runtime.trace.operations

    short_secret = "password123"
    run(runtime.invalidate(short_secret))
    run(runtime.invalidate(short_secret))
    assert dict(runtime.trace.operations)["invalidate"] == 2
    records = [
        r for r in runtime.trace.records if r.operation == "invalidate"
    ]
    assert len(records) == 2
    assert all(
        record.detail is not None and record.detail.startswith("reason#")
        for record in records
    )
    assert records[0].detail == records[1].detail
    assert all(
        record.error_code is None and record.duration_ms >= 0.0
        for record in records
    )

    rendered = runtime.trace.render()
    details = [
        r.get("detail") for r in rendered["records"] if r["operation"] == "invalidate"
    ]
    assert details == [records[0].detail, records[1].detail]
    trace_text = json.dumps(rendered)
    _assert_no_private_identifiers(trace_text)
    assert short_secret not in trace_text
    assert _SECRET_PAYLOAD not in trace_text
    assert observation.revision not in trace_text
    assert all(element.ref not in trace_text for element in observation.elements)
