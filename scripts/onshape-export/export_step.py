#!/usr/bin/env python3
"""Export Onshape Part Studio / Assembly tabs to STEP files.

Talks directly to the Onshape REST API using an API key pair (access key +
secret key), signing requests with Onshape's documented HMAC scheme. This is
independent of FRCDesignApp -- it only needs an Onshape document URL.

Usage:
    export ONSHAPE_ACCESS_KEY=...
    export ONSHAPE_SECRET_KEY=...
    # ...or put ONSHAPE_ACCESS_KEY=/ONSHAPE_SECRET_KEY= in a .env file next to
    # this script (or in the current directory) -- it's loaded automatically.

    # List exportable tabs in a document (no download):
    python export_step.py --url "https://cad.onshape.com/documents/<did>/w/<wid>" --list

    # Export every Part Studio / Assembly tab in a document:
    python export_step.py --url "https://cad.onshape.com/documents/<did>/w/<wid>" --out-dir ./parts

    # Export a single tab:
    python export_step.py --url "https://cad.onshape.com/documents/<did>/w/<wid>/e/<eid>" --out-dir ./parts
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import re
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import formatdate
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://cad.onshape.com"
DEFAULT_API_VERSION = 6
USER_AGENT = "cad-ai-experiment-onshape-export/1.0"
EXPORTABLE_TYPES = {"PARTSTUDIO", "ASSEMBLY"}

URL_RE = re.compile(
    r"/documents/(?P<did>[^/]+)"
    r"(?:/(?P<itype>w|v|m)/(?P<iid>[^/]+))?"
    r"(?:/e/(?P<eid>[^/]+))?"
)


class OnshapeExportError(RuntimeError):
    pass


def load_dotenv(path: Path) -> None:
    """Populates os.environ from a simple KEY=VALUE .env file, if present.

    Existing environment variables always take precedence.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        os.environ.setdefault(key, value)


def make_nonce() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=25))


def sign_request(
    method: str, path: str, query: str, content_type: str, access_key: str, secret_key: str
) -> dict[str, str]:
    nonce = make_nonce()
    date = formatdate(usegmt=True)
    # Onshape's reference signing scheme lowercases the *entire* concatenated
    # string (including the nonce and date), not just path/content-type.
    hmac_str = ("\n".join([method, nonce, date, content_type, path, query]) + "\n").lower()
    signature = base64.b64encode(
        hmac.new(secret_key.encode("utf-8"), hmac_str.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return {
        "Date": date,
        "On-Nonce": nonce,
        "Authorization": f"On {access_key}:HmacSHA256:{signature}",
        "Content-Type": content_type,
        "User-Agent": USER_AGENT,
    }


class OnshapeClient:
    def __init__(self, base_url: str, api_version: int, access_key: str, secret_key: str, timeout: float):
        self.api_root = f"{base_url.rstrip('/')}/api/v{api_version}"
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout = timeout

    def _call(self, method: str, path: str, query: dict[str, str] | None = None, body: Any = None, accept: str = "application/json") -> bytes:
        full_path = urllib.parse.urlparse(self.api_root).path + path
        query_string = urllib.parse.urlencode(sorted((query or {}).items()))
        content_type = "application/json"
        headers = sign_request(method, full_path, query_string, content_type, self.access_key, self.secret_key)
        headers["Accept"] = accept

        url = f"{self.api_root}{path}"
        if query_string:
            url += f"?{query_string}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OnshapeExportError(f"HTTP {exc.code} for {method} {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OnshapeExportError(f"Failed to reach {url}: {exc.reason}") from exc

    def get_json(self, path: str, query: dict[str, str] | None = None) -> Any:
        return json.loads(self._call("GET", path, query=query))

    def post_json(self, path: str, body: Any) -> Any:
        return json.loads(self._call("POST", path, body=body))

    def get_bytes(self, path: str) -> bytes:
        return self._call("GET", path, accept="*/*")


def parse_document_ref(args: argparse.Namespace) -> tuple[str, str, str, str | None]:
    """Returns (documentId, instanceType, instanceId, elementId-or-None)."""
    if args.url:
        parsed = urllib.parse.urlparse(args.url)
        m = URL_RE.search(parsed.path)
        if not m or not m.group("did"):
            raise OnshapeExportError(f"Could not parse an Onshape document URL from: {args.url}")
        did = m.group("did")
        itype = m.group("itype")
        iid = m.group("iid")
        eid = m.group("eid")
        if not itype or not iid:
            itype, iid = "w", None  # resolved below
        return did, itype, iid, eid

    if not args.document_id:
        raise OnshapeExportError("Provide --url or --document-id.")
    return args.document_id, args.instance_type, args.instance_id, args.element_id


def resolve_instance(client: OnshapeClient, did: str, itype: str, iid: str | None) -> tuple[str, str]:
    if iid:
        return itype, iid
    doc = client.get_json(f"/documents/{did}")
    default_ws = doc.get("defaultWorkspace") or {}
    ws_id = default_ws.get("id")
    if not ws_id:
        raise OnshapeExportError(f"Could not resolve default workspace for document {did}.")
    return "w", ws_id


def list_elements(client: OnshapeClient, did: str, itype: str, iid: str) -> list[dict[str, Any]]:
    return client.get_json(f"/documents/d/{did}/{itype}/{iid}/elements")


def sanitize_filename(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return slug or "part"


ELEMENT_TYPE_ROUTE = {
    "PARTSTUDIO": "partstudios",
    "ASSEMBLY": "assemblies",
}


def export_element_to_step(
    client: OnshapeClient,
    did: str,
    itype: str,
    iid: str,
    eid: str,
    el_type: str,
    configuration: str | None,
    poll_interval: float,
    poll_timeout: float,
) -> bytes:
    body = {
        "formatName": "STEP",
        "storeInDocument": False,
    }
    if configuration:
        body["configuration"] = configuration

    route = ELEMENT_TYPE_ROUTE.get(el_type)
    if not route:
        raise OnshapeExportError(f"Don't know how to export element type {el_type!r}.")

    translation = client.post_json(
        f"/{route}/d/{did}/{itype}/{iid}/e/{eid}/translations", body
    )
    translation_id = translation.get("id")
    if not translation_id:
        raise OnshapeExportError(f"Translation request did not return an id: {translation}")

    deadline = time.monotonic() + poll_timeout
    while True:
        status = client.get_json(f"/translations/{translation_id}")
        state = status.get("requestState")
        if state == "DONE":
            break
        if state == "FAILED":
            raise OnshapeExportError(f"Onshape translation failed: {status.get('failureReason', status)}")
        if time.monotonic() > deadline:
            raise OnshapeExportError(f"Translation {translation_id} timed out after {poll_timeout}s (last state: {state}).")
        time.sleep(poll_interval)

    result_doc_id = status.get("resultDocumentId") or did
    external_data_ids = status.get("resultExternalDataIds") or []
    if not external_data_ids:
        raise OnshapeExportError(f"Translation {translation_id} completed with no output file: {status}")

    return client.get_bytes(f"/documents/d/{result_doc_id}/externaldata/{external_data_ids[0]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Onshape Part Studio / Assembly tabs to STEP files.")
    parser.add_argument("--url", help="Onshape document URL (with or without /w|v|m/<id>/e/<elementId>).")
    parser.add_argument("--document-id", help="Onshape documentId (alternative to --url).")
    parser.add_argument("--instance-type", choices=["w", "v", "m"], default="w", help="w=workspace, v=version, m=microversion. Default: w.")
    parser.add_argument("--instance-id", help="Workspace/version/microversion id. If omitted, the default workspace is used.")
    parser.add_argument("--element-id", help="Export only this element (tab). If omitted, all Part Studio/Assembly tabs are exported.")
    parser.add_argument("--types", nargs="+", default=sorted(EXPORTABLE_TYPES), choices=sorted(EXPORTABLE_TYPES), help="Element types to include when exporting a whole document.")
    parser.add_argument("--configuration", help="Onshape configuration string (URL-encoded key=value&... form) applied to every exported element.")
    parser.add_argument("--out-dir", default="./parts", help="Directory to write .step files into. Default: ./parts")
    parser.add_argument("--list", action="store_true", help="List exportable tabs and exit, without downloading anything.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .step files.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Onshape API origin. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--api-version", type=int, default=DEFAULT_API_VERSION, help=f"Onshape API version number. Default: {DEFAULT_API_VERSION}")
    parser.add_argument("--access-key", default=os.environ.get("ONSHAPE_ACCESS_KEY"), help="Onshape API access key. Default: $ONSHAPE_ACCESS_KEY")
    parser.add_argument("--secret-key", default=os.environ.get("ONSHAPE_SECRET_KEY"), help="Onshape API secret key. Default: $ONSHAPE_SECRET_KEY")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request HTTP timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between translation status polls.")
    parser.add_argument("--poll-timeout", type=float, default=120.0, help="Max seconds to wait for a translation to finish.")
    return parser.parse_args()


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv(Path.cwd() / ".env")
    args = parse_args()

    if not args.access_key or not args.secret_key:
        raise SystemExit(
            "Missing Onshape API keys. Set ONSHAPE_ACCESS_KEY / ONSHAPE_SECRET_KEY "
            "or pass --access-key/--secret-key. Generate a pair at "
            "https://cad.onshape.com/appstore/dev-portal"
        )

    client = OnshapeClient(args.base_url, args.api_version, args.access_key, args.secret_key, args.timeout)

    try:
        did, itype, iid, eid_filter = parse_document_ref(args)
        itype, iid = resolve_instance(client, did, itype, iid)

        elements = list_elements(client, did, itype, iid)
        if eid_filter:
            elements = [e for e in elements if e.get("id") == eid_filter]
            if not elements:
                raise OnshapeExportError(f"Element {eid_filter} not found in document {did}.")
        else:
            elements = [e for e in elements if e.get("elementType") in args.types or e.get("type") in args.types]

        if not elements:
            raise OnshapeExportError("No exportable Part Studio / Assembly tabs found.")

        if args.list:
            for el in elements:
                el_type = el.get("elementType") or el.get("type")
                print(f"{el.get('id')}\t{el_type}\t{el.get('name')}")
            return 0

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for el in elements:
            eid = el["id"]
            name = el.get("name", eid)
            el_type = el.get("elementType") or el.get("type")
            filename = sanitize_filename(name) + ".step"
            path = out_dir / filename
            if path.exists() and not args.overwrite:
                print(f"skip (exists): {path}", file=sys.stderr)
                results.append({"elementId": eid, "name": name, "type": el_type, "path": str(path), "skipped": True})
                continue

            print(f"exporting {el_type} '{name}' ({eid}) ...", file=sys.stderr)
            data = export_element_to_step(
                client, did, itype, iid, eid, el_type, args.configuration, args.poll_interval, args.poll_timeout
            )
            path.write_bytes(data)
            results.append({"elementId": eid, "name": name, "type": el_type, "path": str(path), "byteSize": len(data)})

        json.dump({"documentId": did, "instanceType": itype, "instanceId": iid, "exports": results}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except OnshapeExportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
