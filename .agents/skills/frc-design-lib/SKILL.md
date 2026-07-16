---
name: frc-design-lib
description: Search and download COTS (common off-the-shelf) FRC robot parts — motor controllers, power distribution boards, radios, bearings, bushings, and similar hardware — from the FRC Design Lib Onshape library, as STEP files ready to use with the cad skill. Use when the user asks for a specific FRC/robotics COTS part by name or model number (e.g. "roboRIO", "SPARK MAX", "3.75in ID thrust bushing"), wants to browse what's available in FRC Design Lib, or needs a specific configuration/size variant (bearing/bushing sizes, thicknesses) exported as STEP.
---

# FRC Design Lib

Downloads parts from FRC Design Lib — a curated Onshape library of FRC robot
hardware normally browsed inside Onshape via the FRCDesignApp panel — as
local `.step` files, by talking directly to Onshape's REST API. This does
not depend on FRCDesignApp being deployed or reachable; it only needs
Onshape API keys and a hardcoded list of the underlying Onshape documents.

## Document list

`references/documents.json` hardcodes the Onshape documents this skill
searches. Each entry is `{"name": ..., "url": "https://cad.onshape.com/documents/<did>/v/<vid>"}`.
Currently covers all of FRC Design Lib (19 documents, ~610 exportable tabs):
Bearings and Bushings, Fasteners, Gears, Pulleys & Belt Accessories,
Sprockets & Chain Accessories, Wheels, Gearboxes, Spacers & Standoffs,
Shaft & Bearing Accessories, Control System, Sensors & Cameras, Motors &
Servos, Pneumatics, Structure, Extrusions & Shafts, Swerve, Linear Mechanism
Components, Bumper Mounting, and KrayonCAD.

If the user mentions a part that isn't found and they know it lives in
another FRC Design Lib document, add an entry to `documents.json` (get the
document URL from Onshape's Documents list or the FRCDesignApp panel) rather
than guessing at a URL.

## Setup: Onshape API key

Requires an Onshape API key pair with at least "read profile" and "read
documents" permissions (no write/delete/purchase/share needed).

1. Go to https://cad.onshape.com/appstore/dev-portal (the account must have
   access to the FRC Design Lib documents).
2. Create a key pair — copy the access key and secret key immediately (the
   secret is shown once).
3. Put them in `scripts/.env` (already gitignored) next to the scripts:

   ```
   ONSHAPE_ACCESS_KEY=...
   ONSHAPE_SECRET_KEY=...
   ```

   Or export `ONSHAPE_ACCESS_KEY` / `ONSHAPE_SECRET_KEY` as environment
   variables instead — both scripts load `.env` automatically but real env
   vars take precedence.

If a request fails with `"Invalid API key state"`, the key itself is
disabled/stale on Onshape's side — regenerate it at the dev portal.

## Quick workflow

1. **Search** for the part:

   ```bash
   python scripts/search_parts.py "roboRIO"
   python scripts/search_parts.py "thrust bushing" --configs   # also show size/config options
   ```

   Returns JSON: name, elementId, type (`PARTSTUDIO`/`ASSEMBLY`), source
   document, and a ready-to-use `url` per match, ranked by match score. Use
   `--configs` when the part is likely to have size/vendor variants (bearings,
   bushings, breakers) — it attaches each result's configuration parameters
   and named options so you know whether a specific variant needs picking.

2. **If configurable**, either rely on the `--configs` output from step 1, or
   inspect one part directly:

   ```bash
   python scripts/export_part.py --url "<element url>" --list-configs
   ```

3. **Export** to STEP:

   ```bash
   # Default configuration:
   python scripts/export_part.py --url "<element url>" --out-dir <destination>/parts

   # A specific named configuration (repeatable --config, one per parameter):
   python scripts/export_part.py --url "<element url>" \
     --config 'Thickness=1/16"' --config 'Configuration=3.75" ID x 5" OD' \
     --out-dir <destination>/parts

   # Several search results in one call:
   python scripts/export_part.py --url "<url1>" --url "<url2>" --out-dir <destination>/parts
   ```

   Each tab exports via Onshape's Translations API (STEP AP214). Assemblies
   export as a single multi-part STEP. Filenames are the sanitized part name
   (plus the chosen config options, when `--config` is used) — safe to
   re-run into the same `--out-dir`; existing files are skipped unless
   `--overwrite` is passed.

   Put `--out-dir` wherever the downstream CAD work expects reference parts
   — e.g. `demo-models/<project>/parts` next to a `gen_*.py` source, matching
   how `step-parts`' downloader is normally used (see
   `demo-models/step-parts-demo` for that convention).

**Configuration explosion warning**: some parts have dozens to hundreds of
named size/vendor combinations (e.g. one bushing part studio had 146). Don't
export every combination for a part unless the user explicitly asks for the
full size range — pick the specific configuration(s) the task actually needs.

## CAD Viewer Handoff

After exporting `.step` file(s), hand the explicit file path(s) to
`$cad-viewer` when that skill is installed, so the user can visually review
what was downloaded. `$cad-viewer` must start CAD Viewer if not already
running and return review link(s); if unavailable, report that instead of
silently skipping the handoff.

## Notes

- `search_parts.py --list` dumps the entire catalog (all tabs across all
  hardcoded documents) without a query — useful for browsing.
- Search is local fuzzy-name matching (substring + similarity scoring)
  against the tab names Onshape shows in each document; it does not search
  part metadata, descriptions, or FRCDesignApp's own tags.
- If you hit `HTTP 4xx` errors mentioning API versioning, try
  `--api-version 16` on either script.
