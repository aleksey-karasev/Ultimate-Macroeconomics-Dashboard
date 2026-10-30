#!/usr/bin/env python3
"""Initialize every configured MCP server and call one read-only tool.

Run with the repository's services up and secrets in ``.env``:

    uv run --with mcp==2.3.0 python scripts/verify_mcp.py

Optional: ``--only postgres`` (repeatable) and ``--env-file PATH``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import httpx2
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
READ_ONLY_CALLS = {
    "postgres": "list_schemas",
    "clickhouse": "list_databases",
    "grafana": "list_datasources",
    "langfuse": "getHealth",
}
SECRET_ENV_NAMES = {
    "LANGFUSE_MCP_BASIC_AUTH",
    "LANGFUSE_CLICKHOUSE_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
    "POSTGRES_LLM_PASSWORD",
    "LANGFUSE_SECRET_KEY",
}


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _resolve_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if isinstance(value, str):
        return ENV_PATTERN.sub(
            lambda match: os.environ.get(match.group(1), match.group(2) or ""), value
        )
    return value


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name, "")
        if secret:
            message = message.replace(secret, "[redacted]")
    return message or exc.__class__.__name__


async def _exercise(session: ClientSession, name: str) -> None:
    await session.initialize()
    tools = await session.list_tools()
    tool_names = {tool.name for tool in tools.tools}
    expected_call = READ_ONLY_CALLS[name]
    if expected_call not in tool_names:
        raise RuntimeError(
            f"Missing expected read-only tool {expected_call}; got {sorted(tool_names)}"
        )
    result = await session.call_tool(expected_call, arguments={})
    if getattr(result, "isError", False):
        raise RuntimeError(f"Read-only tool {expected_call} returned an error")
    print(f"PASS {name}: initialized, {len(tool_names)} tools, called {expected_call}")


async def _run_server(name: str, config: dict[str, Any]) -> None:
    async with asyncio.timeout(120):
        if config.get("type") == "http":
            async with httpx2.AsyncClient(headers=config.get("headers", {})) as http_client:
                async with streamable_http_client(config["url"], http_client=http_client) as (
                    read_stream,
                    write_stream,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        await _exercise(session, name)
            return

        env = os.environ.copy()
        env.update(config.get("env", {}))
        parameters = StdioServerParameters(
            command=config["command"], args=config.get("args", []), env=env
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await _exercise(session, name)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--only", action="append", choices=sorted(READ_ONLY_CALLS))
    args = parser.parse_args()

    _load_env_file(args.env_file)
    if not os.environ.get("LANGFUSE_MCP_BASIC_AUTH"):
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
        if public_key and secret_key:
            os.environ["LANGFUSE_MCP_BASIC_AUTH"] = base64.b64encode(
                f"{public_key}:{secret_key}".encode()
            ).decode()

    raw_config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    servers = _resolve_env(raw_config["mcpServers"])
    selected = args.only or list(servers)
    failures = 0
    for name in selected:
        try:
            await _run_server(name, servers[name])
        except Exception as exc:  # noqa: BLE001 - report every server before failing
            failures += 1
            print(f"FAIL {name}: {_safe_error(exc)}", file=sys.stderr)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
