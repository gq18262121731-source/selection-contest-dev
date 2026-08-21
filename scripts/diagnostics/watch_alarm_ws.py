from __future__ import annotations

from diag_common import build_parser, error, log, run_async, to_ws_url, watch_ws


def main() -> None:
    parser = build_parser("Watch alarm WebSocket messages.")
    parser.add_argument("--duration", type=float, default=0.0, help="Run seconds. 0 means forever.")
    args = parser.parse_args()
    url = to_ws_url(args.base_url, "/ws/alarms")
    try:
        summary = run_async(watch_ws(url, duration=args.duration))
        log(f"summary {summary}")
    except Exception as exc:
        error(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
