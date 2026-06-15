from __future__ import annotations

from diag_common import build_parser, exit_with_summary, probe_get


def main() -> None:
    parser = build_parser("Probe multimodal omni service status.")
    args = parser.parse_args()
    successes = 0
    failures = 0
    if probe_get(args.base_url, "/api/v1/omni/status", timeout=args.timeout):
        successes += 1
    else:
        failures += 1
    exit_with_summary(successes, failures)


if __name__ == "__main__":
    main()
