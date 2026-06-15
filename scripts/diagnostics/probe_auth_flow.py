from __future__ import annotations

from diag_common import build_parser, error, exit_with_summary, ok, probe_get, request_json, summarize_dict


def main() -> None:
    parser = build_parser("Probe mock auth flow and /auth/me.")
    parser.add_argument("--username", default="", help="Optional username. If omitted, uses first mock account.")
    parser.add_argument("--password", default="", help="Optional password. If omitted, uses first mock account password if present, else 123456.")
    args = parser.parse_args()

    successes = 0
    failures = 0
    if probe_get(args.base_url, "/api/v1/auth/mock-accounts", timeout=args.timeout):
        successes += 1
    else:
        failures += 1

    accounts_ok, accounts, _, _ = request_json("GET", args.base_url, "/api/v1/auth/mock-accounts", timeout=args.timeout)
    username = args.username
    password = args.password
    if accounts_ok and isinstance(accounts, list) and accounts:
        first = accounts[0]
        username = username or str(first.get("username") or first.get("login_username") or "")
        password = password or str(first.get("password") or "123456")
    if not username:
        error("No username available for mock login.")
        exit_with_summary(successes, failures + 1)

    login_payload = {"username": username, "password": password or "123456"}
    login_ok, login_response, elapsed_ms, status = request_json(
        "POST",
        args.base_url,
        "/api/v1/auth/mock-login",
        timeout=args.timeout,
        json_body=login_payload,
    )
    token = None
    if login_ok and isinstance(login_response, dict):
        token = login_response.get("token") or login_response.get("access_token")
        ok(f"POST /auth/mock-login status={status} elapsed={elapsed_ms:.0f}ms {summarize_dict(login_response)}")
        successes += 1
    else:
        error(f"POST /auth/mock-login status={status} elapsed={elapsed_ms:.0f}ms payload={login_response}")
        failures += 1

    if token:
        if probe_get(args.base_url, "/api/v1/auth/me", timeout=args.timeout, token=str(token)):
            successes += 1
        else:
            failures += 1
    else:
        error("mock-login did not return token/access_token; skipping /auth/me")
        failures += 1
    exit_with_summary(successes, failures)


if __name__ == "__main__":
    main()
