from __future__ import annotations

import argparse
import json
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError


SOAP_ENVELOPE = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    {body}
  </s:Body>
</s:Envelope>
"""


def post(url: str, body: str) -> dict[str, object]:
    payload = SOAP_ENVELOPE.format(body=body).encode("utf-8")
    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        method="POST",
    )
    opener = build_opener()
    try:
        with opener.open(req, timeout=8) as resp:
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "text": resp.read().decode("utf-8", errors="replace"),
            }
    except HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {"ok": False, "status": exc.code, "text": text, "error": str(exc)}
    except URLError as exc:
        return {"ok": False, "status": 0, "text": "", "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe ONVIF device/media services without auth.")
    parser.add_argument("--host", default="192.168.8.248")
    parser.add_argument("--device-port", type=int, default=10080)
    args = parser.parse_args()

    urls = [
        f"http://{args.host}:{args.device_port}/onvif/device_service",
        f"http://{args.host}:{args.device_port}/onvif/media_service",
    ]
    tests = {
        "GetCapabilities": '<tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><tds:Category>All</tds:Category></tds:GetCapabilities>',
        "GetProfiles": '<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl" />',
    }

    results: list[dict[str, object]] = []
    for url in urls:
        for name, body in tests.items():
            item = {"url": url, "operation": name}
            item.update(post(url, body))
            results.append(item)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

