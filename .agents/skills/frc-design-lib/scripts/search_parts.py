#!/usr/bin/env python3
"""Search COTS parts across the hardcoded list of FRC Design Lib Onshape documents.

Fetches the tab (Part Studio / Assembly) list from each document in
references/documents.json and fuzzy-matches names against a query. Each
result includes a ready-to-use --url for export_part.py.

Usage:
    python search_parts.py "roboRIO"
    python search_parts.py "bushing" --limit 20
    python search_parts.py "thrust bushing" --configs   # attach configuration options
    python search_parts.py --list                       # dump the whole catalog
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onshape_client import (  # noqa: E402
    DEFAULT_API_VERSION,
    DEFAULT_BASE_URL,
    EXPORTABLE_TYPES,
    OnshapeExportError,
    client_from_env,
    get_configuration,
    list_elements,
    load_default_dotenv,
    parse_document_url,
    resolve_instance,
    summarize_configuration,
)

DOCUMENTS_PATH = Path(__file__).resolve().parent.parent / "references" / "documents.json"


def load_documents() -> list[dict[str, str]]:
    return json.loads(DOCUMENTS_PATH.read_text(encoding="utf-8"))


def build_element_url(did: str, itype: str, iid: str, eid: str) -> str:
    return f"https://cad.onshape.com/documents/{did}/{itype}/{iid}/e/{eid}"


def fetch_catalog(client, documents: list[dict[str, str]], types: set[str]) -> list[dict[str, Any]]:
    catalog = []
    for doc in documents:
        did, itype, iid, _ = parse_document_url(doc["url"])
        itype, iid = resolve_instance(client, did, itype, iid)
        for el in list_elements(client, did, itype, iid):
            el_type = el.get("elementType") or el.get("type")
            if el_type not in types:
                continue
            eid = el["id"]
            catalog.append(
                {
                    "name": el.get("name", eid),
                    "elementId": eid,
                    "type": el_type,
                    "document": doc["name"],
                    "documentId": did,
                    "instanceType": itype,
                    "instanceId": iid,
                    "url": build_element_url(did, itype, iid, eid),
                }
            )
    return catalog


def score_match(query: str, name: str) -> float:
    q, n = query.lower(), name.lower()
    if q in n:
        # Prefer tighter substring matches (query closer to the full name).
        return 1.0 + (len(q) / max(len(n), 1))
    return difflib.SequenceMatcher(None, q, n).ratio()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search COTS parts across FRC Design Lib's Onshape documents.")
    parser.add_argument("query", nargs="?", help="Fuzzy search text, e.g. 'roboRIO' or 'thrust bushing'.")
    parser.add_argument("--list", action="store_true", help="Dump the entire catalog (ignores query/limit/threshold).")
    parser.add_argument("--limit", type=int, default=15, help="Max results to return. Default: 15")
    parser.add_argument("--threshold", type=float, default=0.5, help="Minimum match score (0-1+) to include. Default: 0.5")
    parser.add_argument("--document", help="Restrict search to one manifest document (matched by name, case-insensitive substring).")
    parser.add_argument("--configs", action="store_true", help="Fetch and attach configuration parameters/options for each returned result.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Onshape API origin. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--api-version", type=int, default=DEFAULT_API_VERSION, help=f"Onshape API version number. Default: {DEFAULT_API_VERSION}")
    parser.add_argument("--access-key", default=None, help="Onshape API access key. Default: $ONSHAPE_ACCESS_KEY")
    parser.add_argument("--secret-key", default=None, help="Onshape API secret key. Default: $ONSHAPE_SECRET_KEY")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request HTTP timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    load_default_dotenv()
    args = parse_args()
    client = client_from_env(args)

    try:
        documents = load_documents()
        if args.document:
            documents = [d for d in documents if args.document.lower() in d["name"].lower()]
            if not documents:
                raise OnshapeExportError(f"No manifest document matches --document {args.document!r}.")

        catalog = fetch_catalog(client, documents, EXPORTABLE_TYPES)

        if args.list:
            results = sorted(catalog, key=lambda e: (e["document"], e["name"]))
        elif args.query:
            scored = [(score_match(args.query, e["name"]), e) for e in catalog]
            scored = [(s, e) for s, e in scored if s >= args.threshold]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            results = [{**e, "score": round(s, 3)} for s, e in scored[: args.limit]]
        else:
            raise OnshapeExportError("Provide a query, or use --list to dump the whole catalog.")

        if args.configs:
            for r in results:
                cfg = get_configuration(client, r["documentId"], r["instanceType"], r["instanceId"], r["elementId"])
                params = summarize_configuration(cfg)
                r["configurable"] = bool(params)
                if params:
                    r["configuration"] = params

        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except OnshapeExportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
