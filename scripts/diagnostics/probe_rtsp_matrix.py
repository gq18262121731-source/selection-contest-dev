from __future__ import annotations

import base64
import socket
from dataclasses import dataclass

from diag_common import build_parser, log, ok, error


@dataclass
class RtspCandidate:
    host: str
    port: int
    transport: str
    stream: str
    username: str
    password: str

    @property
    def path(self) -> str:
        return f"/{self.transport}/{self.stream}"

    @property
    def url(self) -> str:
        return f"rtsp://{self.username}:***@{self.host}:{self.port}{self.path}"

    @property
    def real_url(self) -> str:
        return f"rtsp://{self.username}:{self.password}@{self.host}:{self.port}{self.path}"


def send_rtsp(candidate: RtspCandidate, method: str, timeout: float, auth_basic: bool = False) -> tuple[int | None, str]:
    headers = [
        f"{method} rtsp://{candidate.host}:{candidate.port}{candidate.path} RTSP/1.0",
        "CSeq: 1",
        "User-Agent: health-diagnostics",
    ]
    if method == "DESCRIBE":
        headers.append("Accept: application/sdp")
    if auth_basic:
        token = base64.b64encode(f"{candidate.username}:{candidate.password}".encode("utf-8")).decode("ascii")
        headers.append(f"Authorization: Basic {token}")
    payload = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")
    try:
        with socket.create_connection((candidate.host, candidate.port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload)
            data = sock.recv(4096)
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    text = data.decode("latin1", errors="replace")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    parts = first_line.split()
    status = int(parts[1]) if len(parts) >= 2 and parts[0].startswith("RTSP/") and parts[1].isdigit() else None
    return status, text[:600].replace("\r", "\\r").replace("\n", "\\n")


def main() -> None:
    parser = build_parser("Probe RTSP IP/port/path matrix with raw socket OPTIONS/DESCRIBE.")
    parser.add_argument("--hosts", nargs="+", default=["192.168.8.248", "192.168.8.253", "192.168.8.254"])
    parser.add_argument("--ports", nargs="+", type=int, default=[554, 10554])
    parser.add_argument("--transports", nargs="+", default=["tcp", "udp"])
    parser.add_argument("--streams", nargs="+", default=["av0_1", "av0_0"])
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    successes = 0
    failures = 0
    for host in args.hosts:
        for port in args.ports:
            for transport in args.transports:
                for stream in args.streams:
                    candidate = RtspCandidate(
                        host=host,
                        port=port,
                        transport=transport,
                        stream=stream,
                        username=args.username,
                        password=args.password,
                    )
                    log(f"probe {candidate.url}")
                    status, preview = send_rtsp(candidate, "OPTIONS", args.timeout)
                    if status is None:
                        failures += 1
                        error(f"OPTIONS unreachable {candidate.url} detail={preview}")
                        continue
                    log(f"OPTIONS status={status} preview={preview}")
                    describe_status, describe_preview = send_rtsp(candidate, "DESCRIBE", args.timeout)
                    if describe_status in {401, 403}:
                        describe_status, describe_preview = send_rtsp(candidate, "DESCRIBE", args.timeout, auth_basic=True)
                    if describe_status and 200 <= describe_status < 300:
                        successes += 1
                        ok(f"DESCRIBE usable {candidate.url} status={describe_status}")
                    else:
                        failures += 1
                        error(f"DESCRIBE not usable {candidate.url} status={describe_status} preview={describe_preview}")
    log(f"summary rtsp_usable={successes} failed_candidates={failures}")
    raise SystemExit(0 if successes > 0 else 1)


if __name__ == "__main__":
    main()
