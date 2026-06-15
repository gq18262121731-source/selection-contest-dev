from __future__ import annotations

from diag_common import build_parser, exit_with_summary, probe_get


def main() -> None:
    parser = build_parser("Probe Agent, chat capability, and MCP visibility APIs.")
    args = parser.parse_args()
    paths = [
        "/api/v1/agent/elders",
        "/api/v1/chat/capabilities",
        "/api/v1/chat/mcp-tools",
    ]
    successes = 0
    failures = 0
    for path in paths:
        if probe_get(args.base_url, path, timeout=args.timeout):
            successes += 1
        else:
            failures += 1
    exit_with_summary(successes, failures)


if __name__ == "__main__":
    main()
