from __future__ import annotations

from diag_common import (
    DEFAULT_DEVICE_MAC,
    build_parser,
    default_score_payload,
    default_warning_payload,
    exit_with_summary,
    ok,
    error,
    request_json,
    summarize_dict,
)


def main() -> None:
    parser = build_parser("Probe health score and warning APIs.")
    parser.add_argument("--device-mac", default=DEFAULT_DEVICE_MAC, help=f"Device id/mac. Default: {DEFAULT_DEVICE_MAC}")
    args = parser.parse_args()

    checks = [
        ("POST", "/api/v1/health/score", default_score_payload(args.device_mac)),
        ("POST", "/api/v1/health/warning/check", default_warning_payload()),
    ]
    successes = 0
    failures = 0
    for method, path, payload in checks:
        ok_flag, response_payload, elapsed_ms, status = request_json(
            method,
            args.base_url,
            path,
            timeout=args.timeout,
            json_body=payload,
        )
        if ok_flag:
            successes += 1
            compact = summarize_dict(response_payload) if isinstance(response_payload, dict) else str(response_payload)[:200]
            ok(f"{method} {path} status={status} elapsed={elapsed_ms:.0f}ms {compact}")
        else:
            failures += 1
            error(f"{method} {path} status={status} elapsed={elapsed_ms:.0f}ms payload={response_payload}")
    exit_with_summary(successes, failures)


if __name__ == "__main__":
    main()
