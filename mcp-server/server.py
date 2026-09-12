"""External read-only MCP boundary for Praxiom.

This module intentionally lives outside ``src/praxiom``. It may call the
Runtime's read-only operations (status/observe), but it does not expose a raw
mutation tool and therefore cannot bypass the Coordinator as the only mutation
authority. Future write tools must enter through RunSession/SkillExecutor /
ExecutionCoordinator rather than Runtime.execute directly.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import uvicorn
from mcp.server.mcpserver import Context, MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from praxiom.ios_runtime.models import ObserveRequest, RuntimeOperationError
from praxiom.ios_runtime.runtime import NativeIosRuntime
from praxiom.monitor.projection import frame_sink_from_env


HOST = os.environ.get("PRAXIOM_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("PRAXIOM_MCP_PORT", "17679"))
RUNNER_BUNDLE_ID = os.environ.get("PRAXIOM_WDA_RUNNER_BUNDLE_ID") or None
MAX_ELEMENTS_HARD = 500


@dataclass
class AppState:
    runtime: NativeIosRuntime


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _runtime_error(exc: RuntimeOperationError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": exc.code.value,
            "phase": exc.phase.value,
            "effect": exc.effect.value,
            "retry_safe": exc.retry_safe,
            "completed_actions": exc.completed_actions,
            "failed_action_index": exc.failed_action_index,
            "revision_invalidated": exc.revision_invalidated,
        },
    }


def _windows_selector_loop_factory():
    """Create a SelectorEventLoop for Uvicorn on Windows.

    ``pymobiledevice3`` uses selector semantics for Bonjour/RemotePairing on
    Windows. Uvicorn otherwise chooses Proactor when it owns the loop, which
    makes the same paired device disappear from discovery.
    """
    return asyncio.SelectorEventLoop()


@asynccontextmanager
async def _lifespan(_server: MCPServer):
    runtime = NativeIosRuntime(
        xctrunner_bundle_id=RUNNER_BUNDLE_ID,
        frame_sink=frame_sink_from_env(),
    )
    try:
        yield AppState(runtime=runtime)
    finally:
        await runtime.close()


mcp = MCPServer(
    name="praxiom-mcp",
    description=(
        "Read-only external MCP boundary for Praxiom Phase B baseline: "
        "status and observe only; no mutation tool is exposed."
    ),
    version="0.1.0",
    lifespan=_lifespan,
)


def _state(ctx: Context) -> AppState:
    state = ctx.request_context.lifespan_context
    if not isinstance(state, AppState):
        raise RuntimeError("praxiom MCP lifespan state unavailable")
    return state


@mcp.tool(
    name="praxiom_status",
    description="Return Praxiom Runtime lifecycle/transport/WDA status without connecting or mutating the device.",
    structured_output=True,
)
async def praxiom_status(ctx: Context) -> dict[str, Any]:
    status = await _state(ctx).runtime.status()
    return {"ok": True, "status": _jsonable(status), "mode": "read-only"}


@mcp.tool(
    name="praxiom_observe",
    description=(
        "Capture a fresh Praxiom observation through the existing Runtime. "
        "Read-only: returns frame metadata plus bounded accessibility elements; "
        "image bytes are not exposed by this MCP boundary."
    ),
    structured_output=True,
)
async def praxiom_observe(
    ctx: Context,
    sources: list[str] | None = None,
    max_elements: int = 200,
) -> dict[str, Any]:
    requested = frozenset(sources or ("screenshot", "accessibility"))
    if not requested or not requested <= {"screenshot", "accessibility"}:
        return {
            "ok": False,
            "error": {"code": "INVALID_REQUEST", "reason": "sources-invalid"},
        }
    if isinstance(max_elements, bool) or not isinstance(max_elements, int):
        return {
            "ok": False,
            "error": {"code": "INVALID_REQUEST", "reason": "max-elements-invalid"},
        }
    limit = max(0, min(max_elements, MAX_ELEMENTS_HARD))
    try:
        observation = await _state(ctx).runtime.observe(
            ObserveRequest(sources=requested)
        )
    except RuntimeOperationError as exc:
        return _runtime_error(exc)

    elements = list(observation.elements)
    payload = _jsonable(observation)
    payload["elements"] = [_jsonable(item) for item in elements[:limit]]
    return {
        "ok": True,
        "observation": payload,
        "element_count": len(elements),
        "returned_elements": min(len(elements), limit),
        "elements_truncated": len(elements) > limit,
        "mode": "read-only",
    }


_uvicorn_server: uvicorn.Server | None = None


async def _healthz(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "name": "praxiom-mcp",
            "mode": "read-only",
            "mcp": "/mcp",
        }
    )


async def _shutdown(request: Request) -> JSONResponse:
    client = request.client
    host = client.host if client is not None else ""
    if host not in {"127.0.0.1", "::1"}:
        return JSONResponse({"ok": False, "error": "loopback-only"}, status_code=403)
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
    return JSONResponse({"ok": True})


def main() -> None:
    global _uvicorn_server
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=False,
        host=HOST,
    )
    app.routes.insert(0, Route("/healthz", _healthz, methods=["GET"]))
    app.routes.insert(1, Route("/_shutdown", _shutdown, methods=["POST"]))
    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
        loop=_windows_selector_loop_factory if os.name == "nt" else "asyncio",
    )
    _uvicorn_server = uvicorn.Server(config)
    _uvicorn_server.run()


if __name__ == "__main__":
    main()
