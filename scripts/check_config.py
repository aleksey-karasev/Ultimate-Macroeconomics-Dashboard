#!/usr/bin/env python3
"""Static validation for pinned container images and MCP configuration."""

from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MCP_SERVERS = {"postgres", "clickhouse", "grafana", "langfuse"}


def _validate_image(reference: str, location: str) -> None:
    if "@sha256:" in reference:
        return
    if ":" not in reference:
        raise ValueError(f"{location}: image has no exact tag or digest: {reference}")
    tag = reference.rsplit(":", 1)[1]
    if tag == "latest":
        raise ValueError(f"{location}: ':latest' is forbidden: {reference}")
    if not re.search(r"\d+\.\d+", tag):
        raise ValueError(f"{location}: image tag is not an exact version: {reference}")


def check_images() -> int:
    compose = yaml.safe_load((ROOT / "docker-compose.yaml").read_text(encoding="utf-8"))
    checked = 0
    for service_name, service in compose["services"].items():
        image = service.get("image")
        if image:
            _validate_image(image, f"docker-compose.yaml service {service_name}")
            checked += 1

    for dockerfile in sorted(ROOT.glob("*/Dockerfile")):
        for line_number, line in enumerate(
            dockerfile.read_text(encoding="utf-8").splitlines(), start=1
        ):
            location = f"{dockerfile.relative_to(ROOT)}:{line_number}"
            from_match = re.match(r"FROM\s+(\S+)", line)
            if from_match:
                _validate_image(from_match.group(1), location)
                checked += 1
            for copy_match in re.finditer(r"--from=([^\s]+)", line):
                reference = copy_match.group(1)
                if reference not in {"builder", "runtime"}:
                    _validate_image(reference, location)
                    checked += 1
    return checked


def check_mcp() -> None:
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    servers = config.get("mcpServers", {})
    if set(servers) != EXPECTED_MCP_SERVERS:
        raise ValueError(
            f".mcp.json servers must be {sorted(EXPECTED_MCP_SERVERS)}, got {sorted(servers)}"
        )

    for name, package in {
        "postgres": "postgres-mcp",
        "clickhouse": "mcp-clickhouse",
        "grafana": "mcp-grafana",
    }.items():
        server = servers[name]
        if server.get("command") != "uvx" or not server.get("args"):
            raise ValueError(f".mcp.json {name}: expected a pinned uvx package")
        pinned = [arg for arg in server["args"] if arg.startswith(f"{package}==")]
        if len(pinned) != 1 or not pinned[0].split("==", 1)[1]:
            raise ValueError(f".mcp.json {name}: expected {package}==<exact-version>")

    if "scripts/mcp-overrides.txt" not in servers["postgres"]["args"]:
        raise ValueError(".mcp.json postgres: missing scripts/mcp-overrides.txt")
    overrides = ROOT / "scripts" / "mcp-overrides.txt"
    for line in overrides.read_text(encoding="utf-8").splitlines():
        requirement = line.strip()
        if requirement and not requirement.startswith("#") and "==" not in requirement:
            raise ValueError(f"scripts/mcp-overrides.txt: unpinned requirement {requirement}")

    langfuse = servers["langfuse"]
    if langfuse.get("type") != "http" or not langfuse.get("url", "").endswith("/api/public/mcp"):
        raise ValueError(".mcp.json langfuse: invalid HTTP MCP endpoint")
    if "LANGFUSE_MCP_BASIC_AUTH" not in langfuse.get("headers", {}).get("Authorization", ""):
        raise ValueError(".mcp.json langfuse: Authorization must use LANGFUSE_MCP_BASIC_AUTH")


def main() -> None:
    checked = check_images()
    check_mcp()
    print(f"Configuration checks passed ({checked} pinned image references, 4 MCP servers).")


if __name__ == "__main__":
    main()
