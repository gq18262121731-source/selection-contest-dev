from __future__ import annotations

from diag_common import build_parser, exit_with_summary, probe_get


def main() -> None:
    parser = build_parser("Probe care directory and community dashboard APIs.")
    args = parser.parse_args()
    paths = [
        "/api/v1/care/directory",
        "/api/v1/care/access-profile/me",
        "/api/v1/care/community/dashboard",
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
