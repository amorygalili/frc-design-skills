#!/usr/bin/env python3
"""Export Onshape Part Studio / Assembly tabs to STEP files.

Typically used with URLs returned by search_parts.py. Also works against any
Onshape document directly (not just FRC Design Lib).

Usage:
    # Export one part found via search_parts.py:
    python export_part.py --url "https://cad.onshape.com/documents/<did>/v/<vid>/e/<eid>" --out-dir ./parts

    # Export several results from one search_parts.py call in one go:
    python export_part.py --url "<url1>" --url "<url2>" --out-dir ./parts

    # See what tabs exist in a whole document:
    python export_part.py --url "https://cad.onshape.com/documents/<did>/v/<vid>" --list

    # Discover configuration options for a configurable part:
    python export_part.py --url "<element url>" --list-configs

    # Export a specific named configuration:
    python export_part.py --url "<element url>" \\
        --config 'Thickness=1/16"' --config 'Configuration=3.75" ID x 5" OD' \\
        --out-dir ./parts
"""

from __future__ import annotations

import argparse
import json
import os
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
    export_element_to_step,
    get_configuration,
    list_elements,
    load_default_dotenv,
    parse_document_url,
    resolve_configuration_string,
    resolve_instance,
    sanitize_filename,
    summarize_configuration,
)


def resolve_target_elements(client, url: str, types: set[str]) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Returns (documentId, instanceType, instanceId, elements) for one --url."""
    did, itype, iid, eid_filter = parse_document_url(url)
    itype, iid = resolve_instance(client, did, itype, iid)

    elements = list_elements(client, did, itype, iid)
    if eid_filter:
        elements = [e for e in elements if e.get("id") == eid_filter]
        if not elements:
            raise OnshapeExportError(f"Element {eid_filter} not found in document {did}.")
    else:
        elements = [e for e in elements if (e.get("elementType") or e.get("type")) in types]

    if not elements:
        raise OnshapeExportError(f"No exportable Part Studio / Assembly tabs found in {url}.")
    return did, itype, iid, elements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Onshape Part Studio / Assembly tabs to STEP files.")
    parser.add_argument("--url", action="append", default=[], required=True, help="Onshape document or element URL. Repeatable to export several parts in one call.")
    parser.add_argument("--types", nargs="+", default=sorted(EXPORTABLE_TYPES), choices=sorted(EXPORTABLE_TYPES), help="Element types to include when a --url points at a whole document.")
    parser.add_argument("--configuration", help="Raw Onshape-encoded configuration string ('paramId=value;paramId2=value2'). Applies to every exported element; only sensible with a single element target.")
    parser.add_argument("--config", action="append", default=[], metavar="PARAM=OPTION", help="Human-readable configuration choice, e.g. --config 'Thickness=1/16\"'. Repeatable. Requires exactly one targeted element across all --url values.")
    parser.add_argument("--list-configs", action="store_true", help="Print configuration parameters/options for a single targeted element and exit.")
    parser.add_argument("--out-dir", default="./parts", help="Directory to write .step files into. Default: ./parts")
    parser.add_argument("--list", action="store_true", help="List exportable tabs and exit, without downloading anything.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .step files.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Onshape API origin. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--api-version", type=int, default=DEFAULT_API_VERSION, help=f"Onshape API version number. Default: {DEFAULT_API_VERSION}")
    parser.add_argument("--access-key", default=None, help="Onshape API access key. Default: $ONSHAPE_ACCESS_KEY")
    parser.add_argument("--secret-key", default=None, help="Onshape API secret key. Default: $ONSHAPE_SECRET_KEY")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request HTTP timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between translation status polls.")
    parser.add_argument("--poll-timeout", type=float, default=120.0, help="Max seconds to wait for a translation to finish.")
    return parser.parse_args()


def main() -> int:
    load_default_dotenv()
    args = parse_args()
    client = client_from_env(args)

    try:
        targets: list[tuple[str, str, str, dict[str, Any]]] = []
        for url in args.url:
            did, itype, iid, elements = resolve_target_elements(client, url, set(args.types))
            for el in elements:
                targets.append((did, itype, iid, el))

        if args.list:
            for did, itype, iid, el in targets:
                el_type = el.get("elementType") or el.get("type")
                print(f"{el.get('id')}\t{el_type}\t{el.get('name')}\t{did}/{itype}/{iid}")
            return 0

        if args.list_configs:
            if len(targets) != 1:
                raise OnshapeExportError("--list-configs requires exactly one targeted element.")
            did, itype, iid, el = targets[0]
            cfg = get_configuration(client, did, itype, iid, el["id"])
            json.dump(summarize_configuration(cfg), sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0

        configuration = args.configuration
        if args.config:
            if len(targets) != 1:
                raise OnshapeExportError("--config requires exactly one targeted element.")
            if configuration:
                raise OnshapeExportError("Use either --configuration or --config, not both.")
            did, itype, iid, el = targets[0]
            cfg = get_configuration(client, did, itype, iid, el["id"])
            configuration = resolve_configuration_string(cfg, args.config)

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for did, itype, iid, el in targets:
            eid = el["id"]
            name = el.get("name", eid)
            el_type = el.get("elementType") or el.get("type")
            name_suffix = "_" + "_".join(sanitize_filename(v) for v in args.config) if args.config else ""
            filename = sanitize_filename(name) + name_suffix + ".step"
            path = out_dir / filename
            if path.exists() and not args.overwrite:
                print(f"skip (exists): {path}", file=sys.stderr)
                results.append({"elementId": eid, "name": name, "type": el_type, "path": str(path), "skipped": True})
                continue

            print(f"exporting {el_type} '{name}' ({eid}) ...", file=sys.stderr)
            data = export_element_to_step(
                client, did, itype, iid, eid, el_type, configuration, args.poll_interval, args.poll_timeout
            )
            path.write_bytes(data)
            results.append({"elementId": eid, "name": name, "type": el_type, "path": str(path), "byteSize": len(data)})

        json.dump({"exports": results}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except OnshapeExportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
