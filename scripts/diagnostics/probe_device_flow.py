from __future__ import annotations

from diag_common import DEFAULT_DEVICE_MAC, build_parser, exit_with_summary, probe_get


def main() -> None:
    parser = build_parser("Probe device list, detail, bind logs, and serial target visibility.")
    parser.add_argument("--device-mac", default=DEFAULT_DEVICE_MAC, help=f"Device MAC. Default: {DEFAULT_DEVICE_MAC}")
    args = parser.parse_args()

    paths = [
        "/api/v1/devices",
        f"/api/v1/devices/{args.device_mac}",
        f"/api/v1/devices/{args.device_mac}/bind-logs",
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
