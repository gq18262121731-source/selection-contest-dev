from __future__ import annotations

import time

from diag_common import build_parser, log, request_json


def main() -> None:
    parser = build_parser("Continuously watch backend health.")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval seconds. Default: 2")
    parser.add_argument("--duration", type=float, default=0.0, help="Run seconds. 0 means forever.")
    args = parser.parse_args()

    start = time.perf_counter()
    count = 0
    failures = 0
    while True:
        if args.duration > 0 and time.perf_counter() - start >= args.duration:
            break
        count += 1
        ok_flag, payload, elapsed_ms, status = request_json("GET", args.base_url, "/healthz", timeout=args.timeout)
        if ok_flag:
            log(f"healthz ok status={status} elapsed={elapsed_ms:.0f}ms payload={payload}")
        else:
            failures += 1
            log(f"healthz ERROR status={status} elapsed={elapsed_ms:.0f}ms payload={payload}")
        time.sleep(args.interval)
    log(f"summary checks={count} failures={failures}")


if __name__ == "__main__":
    main()
