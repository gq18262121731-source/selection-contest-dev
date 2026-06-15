from __future__ import annotations

import json
import time

import requests

from diag_common import build_parser, error, join_url, log, ok


def main() -> None:
    parser = build_parser("Watch streaming community Agent NDJSON output.")
    parser.add_argument("--provider", default="qwen", choices=["qwen", "tongyi", "ollama", "auto"])
    parser.add_argument("--question", default="请用一句话总结当前社区健康状态。")
    parser.add_argument("--duration", type=float, default=60.0, help="Maximum seconds to wait. Default: 60")
    args = parser.parse_args()

    payload = {
        "question": args.question,
        "role": "community",
        "mode": args.provider,
        "provider": args.provider,
        "workflow": "overview",
        "history_minutes": 60,
        "per_device_limit": 60,
    }
    url = join_url(args.base_url, "/api/v1/chat/analyze/community/stream")
    start = time.perf_counter()
    try:
        with requests.post(url, json=payload, stream=True, timeout=args.timeout) as response:
            log(f"stream opened status={response.status_code} content-type={response.headers.get('content-type', '')}")
            response.raise_for_status()
            ok("reading NDJSON events")
            for line in response.iter_lines(decode_unicode=True):
                if args.duration > 0 and time.perf_counter() - start >= args.duration:
                    break
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    log(f"raw {line[:300]}")
                    continue
                event_type = event.get("type", "unknown")
                detail = event.get("stage") or event.get("status") or event.get("delta") or event.get("answer") or ""
                log(f"event={event_type} detail={str(detail)[:220]}")
    except Exception as exc:
        error(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
