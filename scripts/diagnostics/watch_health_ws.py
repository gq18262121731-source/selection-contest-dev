from __future__ import annotations

from diag_common import DEFAULT_DEVICE_MAC, build_parser, error, log, run_async, to_ws_url, watch_ws


def main() -> None:
    parser = build_parser("Watch realtime health WebSocket for one device.")
    parser.add_argument("--device-mac", default=DEFAULT_DEVICE_MAC, help=f"Device MAC. Default: {DEFAULT_DEVICE_MAC}")
    parser.add_argument("--duration", type=float, default=0.0, help="Run seconds. 0 means forever.")
    args = parser.parse_args()
    url = to_ws_url(args.base_url, f"/ws/health/{args.device_mac}")
    try:
        summary = run_async(watch_ws(url, duration=args.duration))
        log(f"summary {summary}")
    except Exception as exc:
        error(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
