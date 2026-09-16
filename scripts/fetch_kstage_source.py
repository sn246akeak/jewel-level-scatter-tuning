#!/usr/bin/env python3
"""Fetch a KStage V2 source state into a reusable source-state artifact."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from board_common import write_json


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class KStageAPIError(ValueError):
    """A sanitized transport failure which the normal CLI can report without a traceback."""


def fetch_bundle(url: str, report_path: Path | None = None) -> tuple[dict, dict]:
    parsed = urlparse(url)
    token = parse_qs(parsed.query).get("open_token", [None])[0]
    if not token:
        raise ValueError("KStage URL is missing open_token")
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    report = {"schema": "kstage-prepare-report-v1", "started_at": utc_now(),
              "status": "running", "requests": [], "browser_writes": 0}
    secrets = [token]

    def redact(text):
        for secret in secrets:
            if secret:
                text = text.replace(secret, "<redacted>")
        return text

    def persist():
        if report_path:
            write_json(report_path, report)

    def post(endpoint, body):
        event = {"endpoint": endpoint, "started_at": utc_now(), "status": "pending"}
        for key in ("requestId", "expectedRevision"):
            if key in body:
                event[key] = body[key]
        if "operation" in body:
            event["operation"] = body["operation"]
        report["requests"].append(event)
        persist()
        start = monotonic()
        request = Request(f"{base}/api/v2/{endpoint}", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            try:
                with urlopen(request, timeout=30) as response:
                    event["http_status"] = response.status
                    raw = response.read().decode("utf-8", errors="replace")
            except HTTPError as error:
                event["http_status"] = error.code
                raw = error.read().decode("utf-8", errors="replace")
            except (URLError, TimeoutError) as error:
                raise KStageAPIError(f"E_API: {endpoint}: {redact(str(error))}") from None
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = None
            if event["http_status"] >= 400 or not isinstance(result, dict) or result.get("ok") is False:
                event["response_body"] = redact(raw)
                code = result.get("code", "request_failed") if isinstance(result, dict) else "invalid_json"
                message = result.get("error", "Request rejected") if isinstance(result, dict) else "Non-JSON response"
                event["server_code"] = code
                raise KStageAPIError(f"E_API: {endpoint}: HTTP {event['http_status']} {code}: {redact(str(message))}")
            event["status"] = "passed"
            return result
        except KStageAPIError as error:
            event["status"] = "failed"
            event["error"] = str(error)
            raise
        finally:
            event["finished_at"] = utc_now()
            event["elapsed_seconds"] = round(monotonic() - start, 3)
            persist()

    try:
        payload = post("bootstrap", {"openToken": token})
        state = payload.get("state")
        if not isinstance(state, dict) or not state.get("source", {}).get("completeBoard"):
            raise ValueError("E_SOURCE: KStage bootstrap response does not contain a source board")
        secrets.append(payload["contextToken"])
        report["source"] = {"identity": state["identity"], "revision": state["revision"],
                            "source_sha256": state["source"]["sourceSha256"], "grid": state["source"]["grid"]}
        started = post("prefill/start", {
            "contextToken": payload["contextToken"], "requestId": str(uuid.uuid4()),
            "expectedRevision": state["revision"], "state": state,
            "operation": {"occurredAt": utc_now()},
        })
        blocks = started.get("result", {}).get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("E_BLOCKS_MISSING: prefill/start did not return real KStage blocks")
        report["block_count"] = len(blocks)
        report["status"] = "passed"
        return state, {"schema": "kstage-source-blocks-v1", "identity": state["identity"],
                       "source_revision": state["source"]["sourceSha256"],
                       "completeBoard": state["source"]["completeBoard"], "blocks": blocks}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = redact(str(error))
        raise
    finally:
        report["finished_at"] = utc_now()
        persist()


def fetch(url: str) -> dict:
    return fetch_bundle(url)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, default=Path("source-state.json"))
    args = parser.parse_args()
    write_json(args.output, fetch(args.url))
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
