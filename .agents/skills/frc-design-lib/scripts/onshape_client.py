"""Shared Onshape REST API client for the frc-design-lib skill.

Signs requests with an API key pair (access key + secret key) using
Onshape's documented HMAC scheme. No third-party dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import re
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import formatdate
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://cad.onshape.com"
DEFAULT_API_VERSION = 6
USER_AGENT = "frc-design-lib-skill/1.0"
EXPORTABLE_TYPES = {"PARTSTUDIO", "ASSEMBLY"}
ELEMENT_TYPE_ROUTE = {
    "PARTSTUDIO": "partstudios",
    "ASSEMBLY": "assemblies",
}

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


def load_default_dotenv() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv(Path.cwd() / ".env")


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


def client_from_env(args) -> OnshapeClient:
    access_key = getattr(args, "access_key", None) or os.environ.get("ONSHAPE_ACCESS_KEY")
    secret_key = getattr(args, "secret_key", None) or os.environ.get("ONSHAPE_SECRET_KEY")
    if not access_key or not secret_key:
        raise SystemExit(
            "Missing Onshape API keys. Set ONSHAPE_ACCESS_KEY / ONSHAPE_SECRET_KEY "
            "(env var or .env file next to this script) or pass --access-key/--secret-key. "
            "Generate a pair at https://cad.onshape.com/appstore/dev-portal"
        )
    base_url = getattr(args, "base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
    api_version = getattr(args, "api_version", DEFAULT_API_VERSION) or DEFAULT_API_VERSION
    timeout = getattr(args, "timeout", 30.0) or 30.0
    return OnshapeClient(base_url, api_version, access_key, secret_key, timeout)


def parse_document_url(url: str) -> tuple[str, str | None, str | None, str | None]:
    """Returns (documentId, instanceType-or-None, instanceId-or-None, elementId-or-None)."""
    parsed = urllib.parse.urlparse(url)
    m = URL_RE.search(parsed.path)
    if not m or not m.group("did"):
        raise OnshapeExportError(f"Could not parse an Onshape document URL from: {url}")
    return m.group("did"), m.group("itype"), m.group("iid"), m.group("eid")


def resolve_instance(client: OnshapeClient, did: str, itype: str | None, iid: str | None) -> tuple[str, str]:
    if iid:
        return itype or "w", iid
    doc = client.get_json(f"/documents/{did}")
    default_ws = doc.get("defaultWorkspace") or {}
    ws_id = default_ws.get("id")
    if not ws_id:
        raise OnshapeExportError(f"Could not resolve default workspace for document {did}.")
    return "w", ws_id


def list_elements(client: OnshapeClient, did: str, itype: str, iid: str) -> list[dict[str, Any]]:
    return client.get_json(f"/documents/d/{did}/{itype}/{iid}/elements")


def get_configuration(client: OnshapeClient, did: str, itype: str, iid: str, eid: str) -> dict[str, Any]:
    return client.get_json(f"/elements/d/{did}/{itype}/{iid}/e/{eid}/configuration")


def summarize_configuration(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Turns a raw BTConfigurationResponse into a compact, human-readable list."""
    summary = []
    for p in cfg.get("configurationParameters", []):
        bt = p.get("btType", "")
        entry: dict[str, Any] = {
            "parameterId": p.get("parameterId"),
            "parameterName": p.get("parameterName"),
            "default": p.get("defaultValue"),
        }
        if "Enum" in bt:
            entry["type"] = "enum"
            entry["options"] = [
                {"name": o.get("optionName"), "value": o.get("option")}
                for o in p.get("options", [])
            ]
        elif "Boolean" in bt:
            entry["type"] = "boolean"
        elif "Quantity" in bt:
            entry["type"] = "quantity"
            entry["rangeAndDefault"] = p.get("rangeAndDefault")
        else:
            entry["type"] = "string"
        summary.append(entry)
    return summary


def resolve_configuration_string(cfg: dict[str, Any], pairs: list[str]) -> str:
    """Resolves ["Parameter Name=Option Name", ...] into Onshape's encoded
    configuration body string ("paramId=value;paramId2=value2...") by
    matching human-readable parameter/option names against the live schema.
    """
    params_by_name = {
        p.get("parameterName", "").lower(): p for p in cfg.get("configurationParameters", [])
    }

    resolved: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise OnshapeExportError(f"--config value must be 'Parameter Name=Option Name', got: {pair!r}")
        param_name, _, option_name = pair.partition("=")
        param_name, option_name = param_name.strip(), option_name.strip()

        param = params_by_name.get(param_name.lower())
        if not param:
            available = ", ".join(p.get("parameterName", "?") for p in cfg.get("configurationParameters", []))
            raise OnshapeExportError(f"Unknown configuration parameter {param_name!r}. Available: {available}")

        param_id = param["parameterId"]
        if "Enum" in param.get("btType", ""):
            options = {o.get("optionName", "").lower(): o.get("option") for o in param.get("options", [])}
            value = options.get(option_name.lower())
            if value is None:
                available = ", ".join(o.get("optionName", "?") for o in param.get("options", []))
                raise OnshapeExportError(
                    f"Unknown option {option_name!r} for parameter {param_name!r}. Available: {available}"
                )
        else:
            # Quantity/boolean/string parameters: pass the given value straight through.
            value = option_name

        resolved[param_id] = value

    return ";".join(f"{pid}={urllib.parse.quote(value, safe='')}" for pid, value in resolved.items())


def sanitize_filename(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return slug or "part"


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
    body: dict[str, Any] = {
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
