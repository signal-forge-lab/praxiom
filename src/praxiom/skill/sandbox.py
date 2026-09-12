"""R8-D Sandboxed candidate execution (smallest sufficient same-host boundary)."""
from __future__ import annotations

import builtins
import dis
import inspect
import math
import sys
import time
import types
from dataclasses import dataclass
from typing import Any, Callable

from praxiom.skill.candidate import BANNED_TOKENS

__all__ = ["SandboxPolicy", "SandboxResult", "run_sandboxed", "Cancelled"]

MAX_STEPS_HARD = 64
MAX_DATA_NODES = 256
MAX_SCALAR_BYTES = 8192
MAX_INT_BITS = 256
MAX_CODE_INSTRUCTIONS = 256
MAX_OPCODE_EVENTS = 1_000_000


class Cancelled(Exception):
    pass


class _SandboxTimedOut(BaseException):
    """Private control-flow signal that ordinary step exceptions cannot catch."""


class _SandboxCancelled(BaseException):
    """Private control-flow signal for asynchronous cancellation."""


class _SandboxResourceExhausted(BaseException):
    """Private control-flow signal for the hard instruction budget."""


@dataclass(frozen=True, kw_only=True)
class SandboxPolicy:
    max_steps: int = 8
    deadline_ms: int = 1000
    allow_network: bool = False
    allow_filesystem: bool = False
    allow_credentials: bool = False
    allow_device: bool = False
    cancellable: bool = True


@dataclass(frozen=True, kw_only=True)
class SandboxResult:
    ok: bool
    steps_used: int
    timed_out: bool
    cancelled: bool
    detail: str
    device_calls: int = 0  # sandbox itself always 0


StepFn = Callable[[dict[str, Any], dict[str, Any]], tuple[str, dict[str, Any]]]

_SAFE_GLOBALS = {
    "ValueError": builtins.ValueError,
    "RuntimeError": builtins.RuntimeError,
    "AssertionError": builtins.AssertionError,
    "Cancelled": Cancelled,
}
_EXTRA_DENY = frozenset({
    "__import__", "eval", "exec", "compile", "open", "globals", "locals",
    "getattr", "setattr", "delattr", "vars", "input", "socket",
    "breakpoint", "help", "exit", "quit", "print", "pow", "range",
    "sum", "sorted", "min", "max", "any", "all", "bytes", "bytearray",
    "list", "set", "tuple", "dict", "memoryview", "BaseException",
})
_DANGEROUS_BINARY_OPS = frozenset({"*", "*=", "**", "**=", "<<", "<<=", "@", "@=", "%", "%="})
_ATTRIBUTE_OPS = frozenset({"LOAD_ATTR", "LOAD_METHOD", "STORE_ATTR", "DELETE_ATTR"})
_UNSUPPORTED_CONTROL_OPS = frozenset({
    "RETURN_GENERATOR", "YIELD_VALUE", "YIELD_FROM", "GET_AWAITABLE",
    # BUILD_STRING is excluded so generated formatting has one clear,
    # fail-closed rule. FORMAT_* opcodes are rejected separately below because
    # CPython renamed/split them across 3.12-3.14 (FORMAT_VALUE,
    # FORMAT_SIMPLE, FORMAT_WITH_SPEC).
    "BUILD_STRING",
})
_EXTERNAL_MUTATION_OPS = frozenset({
    "STORE_GLOBAL", "DELETE_GLOBAL", "STORE_DEREF", "DELETE_DEREF", "STORE_NAME", "DELETE_NAME",
})


def _safe_data(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
    counter: list[int] | None = None,
) -> bool:
    if depth > 6:
        return False
    seen = seen if seen is not None else set()
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_DATA_NODES:
        return False
    value_type = type(value)
    if value is None or value_type is bool:
        return True
    if value_type is int:
        return value.bit_length() <= MAX_INT_BITS
    if value_type is float:
        return math.isfinite(value)
    if value_type in (str, bytes):
        return len(value) <= MAX_SCALAR_BYTES
    if value_type in (tuple, list, set, frozenset):
        oid = id(value)
        if oid in seen:
            return False
        seen.add(oid)
        ok = all(_safe_data(v, depth=depth + 1, seen=seen, counter=counter) for v in value)
        seen.remove(oid)
        return ok
    if value_type is dict:
        oid = id(value)
        if oid in seen:
            return False
        seen.add(oid)
        ok = all(
            _safe_data(k, depth=depth + 1, seen=seen, counter=counter)
            and _safe_data(v, depth=depth + 1, seen=seen, counter=counter)
            for k, v in value.items()
        )
        seen.remove(oid)
        return ok
    return False


def _safe_capture_data(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
    counter: list[int] | None = None,
) -> bool:
    """Admit only deeply immutable data from caller-owned captures.

    The step receives an isolated mutable state copy.  Globals, closures, and
    defaults are different: mutating one would escape the pure-function
    boundary into host-owned memory, so only immutable scalar/tuple/frozenset
    values are allowed there.
    """
    if depth > 6:
        return False
    seen = seen if seen is not None else set()
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_DATA_NODES:
        return False
    value_type = type(value)
    if value is None or value_type is bool:
        return True
    if value_type is int:
        return value.bit_length() <= MAX_INT_BITS
    if value_type is float:
        return math.isfinite(value)
    if value_type in (str, bytes):
        return len(value) <= MAX_SCALAR_BYTES
    if value_type in (tuple, frozenset):
        oid = id(value)
        if oid in seen:
            return False
        seen.add(oid)
        ok = all(
            _safe_capture_data(v, depth=depth + 1, seen=seen, counter=counter)
            for v in value
        )
        seen.remove(oid)
        return ok
    return False


def _clone_safe_data(value: Any) -> Any:
    """Deep-copy already-validated sandbox data without invoking user hooks."""
    value_type = type(value)
    if value is None or value_type in (bool, int, float, str, bytes):
        return value
    if value_type is tuple:
        return tuple(_clone_safe_data(v) for v in value)
    if value_type is list:
        return [_clone_safe_data(v) for v in value]
    if value_type is set:
        return {_clone_safe_data(v) for v in value}
    if value_type is frozenset:
        return frozenset(_clone_safe_data(v) for v in value)
    if value_type is dict:
        return {_clone_safe_data(k): _clone_safe_data(v) for k, v in value.items()}
    raise TypeError("unsafe-data-clone")


def _code_strings(code: types.CodeType) -> list[str]:
    out: list[str] = [*code.co_names, *code.co_freevars]
    for const in code.co_consts:
        if isinstance(const, str):
            out.append(const)
        elif isinstance(const, types.CodeType):
            out.extend(_code_strings(const))
    return out


def _contains_import_opcode(code: types.CodeType) -> bool:
    for instruction in dis.get_instructions(code):
        if instruction.opname in {"IMPORT_NAME", "IMPORT_FROM"}:
            return True
    return any(
        _contains_import_opcode(c)
        for c in code.co_consts
        if isinstance(c, types.CodeType)
    )


def _code_static_error(code: types.CodeType) -> str | None:
    nested = [c for c in code.co_consts if isinstance(c, types.CodeType)]
    if nested:
        return "unsafe-step-nested-code"
    if code.co_exceptiontable:
        # Trace-raised deadline/cancellation signals must not be catchable by
        # untrusted code.  The smallest sufficient procedural subset does not
        # require local try/except/finally handlers.
        return "unsafe-step-exception-handler"
    instructions = list(dis.get_instructions(code))
    if len(instructions) > MAX_CODE_INSTRUCTIONS:
        return "unsafe-step-code-size"
    for instruction in instructions:
        if instruction.opname in _ATTRIBUTE_OPS:
            return f"unsafe-step-opcode:{instruction.opname.lower()}"
        if instruction.opname in _EXTERNAL_MUTATION_OPS:
            return f"unsafe-step-opcode:{instruction.opname.lower()}"
        if instruction.opname in _UNSUPPORTED_CONTROL_OPS or instruction.opname.startswith("FORMAT_"):
            return f"unsafe-step-opcode:{instruction.opname.lower()}"
        if instruction.opname == "BINARY_OP" and instruction.argrepr in _DANGEROUS_BINARY_OPS:
            return f"unsafe-step-binary-op:{instruction.argrepr}"
    for const in code.co_consts:
        if isinstance(const, (int, float, str, bytes)) and not _safe_data(const):
            return "unsafe-step-constant"
    return None


def _step_static_error(step: StepFn) -> str | None:
    if not inspect.isfunction(step):
        return "step-must-be-plain-function"
    # Avoid invoking user-defined mapping hooks while inspecting resolution of
    # globals/builtins. Ordinary module functions use exact dicts here.
    if type(step.__globals__) is not dict or type(step.__builtins__) is not dict:
        return "unsafe-step-globals-container"
    code = step.__code__
    if _contains_import_opcode(code):
        return "unsafe-step-import"
    code_error = _code_static_error(code)
    if code_error:
        return code_error
    lowered = [x.lower() for x in _code_strings(code)]
    for item in lowered:
        if item.startswith("__") or item in _EXTRA_DENY:
            return f"unsafe-step-symbol:{item}"
        for token in BANNED_TOKENS:
            if token in item:
                return f"unsafe-step-symbol:{token}"
    for name in code.co_names:
        if name in _SAFE_GLOBALS:
            expected = _SAFE_GLOBALS[name]
            resolved = step.__globals__.get(name, step.__builtins__.get(name))
            if resolved is not expected:
                return f"unsafe-step-global:{name}"
            continue
        if name in step.__globals__:
            value = step.__globals__[name]
            if not _safe_capture_data(value):
                return f"unsafe-step-global:{name}"
            continue
        # Python otherwise resolves names through implicit builtins.  Keep the
        # untrusted surface closed: only the explicit exception constructors
        # above are admitted.
        return f"unsafe-step-implicit-global:{name}"
    closure = step.__closure__ or ()
    for cell in closure:
        try:
            value = cell.cell_contents
        except ValueError:
            return "unsafe-empty-closure"
        if not _safe_capture_data(value):
            return "unsafe-step-closure"
    defaults = step.__defaults__ or ()
    if not all(_safe_capture_data(v) for v in defaults):
        return "unsafe-step-default"
    kwdefaults = step.__kwdefaults__ or {}
    if not all(_safe_capture_data(v) for v in kwdefaults.values()):
        return "unsafe-step-default"
    return None


def run_sandboxed(
    step: StepFn,
    *,
    initial_state: dict[str, Any],
    policy: SandboxPolicy,
    now_ms: Callable[[], int] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> SandboxResult:
    """Run untrusted procedural steps with step/deadline/cancel bounds.

    Fail-closed: policy with device/network/fs/credential authority is rejected
    before any step; cancellation/deadline/resource exhaustion stops execution.
    The sandbox makes zero device calls by construction.
    """
    clock = now_ms or (lambda: int(time.monotonic() * 1000))
    cancelled = is_cancelled or (lambda: False)
    if policy.allow_network or policy.allow_filesystem or policy.allow_credentials or policy.allow_device:
        return SandboxResult(ok=False, steps_used=0, timed_out=False,
                             cancelled=False, detail="policy-exceeds-minimal-boundary")
    if policy.max_steps < 1 or policy.max_steps > MAX_STEPS_HARD or policy.deadline_ms < 1:
        return SandboxResult(ok=False, steps_used=0, timed_out=False,
                             cancelled=False, detail="invalid-bounds")
    if not policy.cancellable:
        return SandboxResult(ok=False, steps_used=0, timed_out=False,
                             cancelled=False, detail="cancellation-required")
    if type(initial_state) is not dict or not _safe_data(initial_state):
        return SandboxResult(ok=False, steps_used=0, timed_out=False,
                             cancelled=False, detail="unsafe-initial-state")
    static_error = _step_static_error(step)
    if static_error:
        return SandboxResult(ok=False, steps_used=0, timed_out=False,
                             cancelled=False, detail=static_error)
    start = clock()
    wall_start_ns = time.monotonic_ns()
    wall_deadline_ns = wall_start_ns + (policy.deadline_ms * 1_000_000)
    state = _clone_safe_data(initial_state)
    budget = {"steps_left": policy.max_steps}
    steps = 0

    opcode_events = 0

    def _check_interrupts(frame=None) -> None:
        nonlocal opcode_events
        if cancelled():
            raise _SandboxCancelled()
        if time.monotonic_ns() >= wall_deadline_ns or clock() - start >= policy.deadline_ms:
            raise _SandboxTimedOut()
        opcode_events += 1
        if opcode_events > MAX_OPCODE_EVENTS:
            raise _SandboxResourceExhausted()
        if frame is not None:
            # Re-check step-local values at opcode boundaries so bounded input
            # cannot be amplified repeatedly inside one non-returning step.
            # A single primitive operation may transiently exceed the bound on
            # the VM stack, but it is rejected before another opcode can use a
            # stored oversized value.
            local_counter = [0]
            local_seen: set[int] = set()
            for value in frame.f_locals.values():
                if not _safe_data(value, seen=local_seen, counter=local_counter):
                    raise _SandboxResourceExhausted()

    def _trace(frame, event, arg):
        if frame.f_code is not step.__code__:
            return None
        if event == "call":
            # Keep line events enabled as a portable fallback. Some supported
            # CPython builds accept f_trace_opcodes=True without emitting
            # opcode callbacks for an ordinarily imported/compiled function;
            # line events still recur in a non-returning loop and therefore
            # preserve deadline/cancellation preemption.
            frame.f_trace_lines = True
            frame.f_trace_opcodes = True
            _check_interrupts(frame)
            return _trace
        if event in ("line", "opcode"):
            _check_interrupts(frame)
        return _trace

    try:
        while budget["steps_left"] > 0:
            if cancelled():
                return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                                     cancelled=True, detail="cancelled-before-step")
            if clock() - start >= policy.deadline_ms:
                return SandboxResult(ok=False, steps_used=steps, timed_out=True,
                                     cancelled=False, detail="deadline-exceeded")
            previous_trace = sys.gettrace()
            try:
                sys.settrace(_trace)
                effect, state = step(_clone_safe_data(state), _clone_safe_data(budget))
            finally:
                sys.settrace(previous_trace)
            steps += 1
            budget["steps_left"] -= 1
            if type(state) is not dict or not _safe_data(state):
                return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                                     cancelled=False, detail="unsafe-step-state")
            if cancelled():
                return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                                     cancelled=True, detail="cancelled-after-step")
            if clock() - start >= policy.deadline_ms:
                return SandboxResult(ok=False, steps_used=steps, timed_out=True,
                                     cancelled=False, detail="deadline-exceeded")
            if type(effect) is not str:
                return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                                     cancelled=False, detail="unsafe-step-effect")
            if effect == "done":
                return SandboxResult(ok=True, steps_used=steps, timed_out=False,
                                     cancelled=False, detail="completed")
            if effect not in ("continue", "done"):
                return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                                     cancelled=False, detail=f"unrecognized-effect:{effect}")
        return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                             cancelled=False, detail="step-budget-exhausted")
    except _SandboxTimedOut:
        return SandboxResult(ok=False, steps_used=steps, timed_out=True,
                             cancelled=False, detail="deadline-exceeded-during-step")
    except _SandboxCancelled:
        return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                             cancelled=True, detail="cancelled-during-step")
    except _SandboxResourceExhausted:
        return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                             cancelled=False, detail="instruction-budget-exhausted")
    except Cancelled:
        return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                             cancelled=True, detail="cancelled-during-step")
    except BaseException as exc:
        return SandboxResult(ok=False, steps_used=steps, timed_out=False,
                             cancelled=False, detail=f"step-error:{type(exc).__name__}")
