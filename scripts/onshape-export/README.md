# Onshape STEP export

Downloads Part Studio / Assembly tabs from an Onshape document as `.step`
files, so they can be used locally as reference parts with the CAD skills in
`.agents/skills` (see `demo-models/step-parts-demo` for how downloaded parts
are typically wired into a `gen_*.py` source). This talks directly to
Onshape's REST API and doesn't depend on FRCDesignApp.

## 1. Get an Onshape API key

1. Go to https://cad.onshape.com/appstore/dev-portal (log in with the account
   that has access to the FRC Design Lib documents).
2. Create an API key pair. Onshape shows the secret key once — copy both
   values immediately.
3. Set them as environment variables:

   ```sh
   export ONSHAPE_ACCESS_KEY="..."
   export ONSHAPE_SECRET_KEY="..."
   ```

   Or put them in a `.env` file next to `export_step.py` (or in your current
   directory) — it's loaded automatically and is already gitignored:

   ```
   ONSHAPE_ACCESS_KEY=...
   ONSHAPE_SECRET_KEY=...
   ```

## 2. Find the document

Open FRC Design Lib inside Onshape (however you normally reach it — the
FRCDesignApp panel, a shared link, or Onshape's Documents search) and copy
the document URL from the browser address bar, e.g.:

```
https://cad.onshape.com/documents/<documentId>/w/<workspaceId>
https://cad.onshape.com/documents/<documentId>/w/<workspaceId>/e/<elementId>   # a single tab
```

If FRCDesignApp organizes the library as several separate Onshape documents
("groups"), repeat this for each document/group you want.

## 3. List what's exportable (optional)

```sh
python export_step.py --url "https://cad.onshape.com/documents/<did>/w/<wid>" --list
```

Prints `elementId  TYPE  name` for every Part Studio / Assembly tab.

## 4. Export

Whole document:

```sh
python export_step.py \
  --url "https://cad.onshape.com/documents/<did>/w/<wid>" \
  --out-dir ../../demo-models/frc-design-lib/parts
```

Single tab:

```sh
python export_step.py \
  --url "https://cad.onshape.com/documents/<did>/w/<wid>/e/<eid>" \
  --out-dir ../../demo-models/frc-design-lib/parts
```

Each tab is exported via Onshape's Translations API (STEP AP214) and written
as `<sanitized-name>.step`. Configurable parts (see below) export with their
default configuration unless you pass `--config`.

## 5. Configurable parts

Many library parts (bushings, bearings, etc.) are one Part Studio with dozens
of size/option variants via Onshape configurations. Exporting "everything"
for a heavily configured part can mean hundreds of files, so by default you
only get the default configuration — pick specific ones explicitly.

List the available parameters/options for a single tab:

```sh
python export_step.py \
  --url "https://cad.onshape.com/documents/<did>/v/<vid>/e/<eid>" \
  --list-configs
```

This prints each parameter's name and, for enum parameters, every named
option (e.g. `"3.75\" ID x 5\" OD"`). Then export a specific combination by
human-readable name — `--config` is repeatable, one per parameter:

```sh
python export_step.py \
  --url "https://cad.onshape.com/documents/<did>/v/<vid>/e/<eid>" \
  --config 'Thickness=1/16"' \
  --config 'Configuration=3.75" ID x 5" OD' \
  --out-dir ../../demo-models/frc-design-lib/bearings-and-bushings
```

The output filename includes the chosen option names so different sizes of
the same part don't collide (e.g.
`thrust_bushing_mcm_thickness_1_16_configuration_3_75_id_x_5_od.step`).
`--config` only works when exactly one tab is targeted (via `--element-id`
or a `/e/<id>` URL) — the parameter/option names are specific to that part's
configuration schema.

If you already have Onshape's raw encoded configuration string (e.g. copied
from a URL), pass it directly with `--configuration "paramId=value;paramId2=value2"`
instead of `--config`.

## Notes

- Assemblies export as a single multi-part STEP (matches how FRCDesignApp
  treats an assembly tab as one insertable).
- Re-running with the same `--out-dir` skips files that already exist; pass
  `--overwrite` to re-download.
- If you hit `HTTP 4xx` errors mentioning API versioning, try
  `--api-version 16` (the version FRCDesignApp itself pins in
  `wrangler.jsonc`).
