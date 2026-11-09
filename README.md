# Heart and Chest Radar

Interactive research laboratory for the CSCI 4850/6850 final project, by Allan Gramajo and Alan Acosta.

**Project site after a successful Pages deployment:** https://allangramajo.github.io/Heart-and-Chest-radar/

[Deployment runs](https://github.com/AllanGramajo/Heart-and-Chest-radar/actions/workflows/deploy.yml) · [Pages settings](https://github.com/AllanGramajo/Heart-and-Chest-radar/settings/pages)

## Enable publication

1. Open **Settings → Pages** and set **Build and deployment → Source → GitHub Actions**.
2. Open **Actions → Build recording and publish website**. A push to `main` starts the workflow. To retry after changing Pages settings, use **Run workflow** on `main`, or rerun the failed deployment.
3. Open the project site only after the build and deployment succeed. A repository existing is not proof that a website is live.

No local CSV download, upload, account, or installation is required for visitors. The build downloads one public MobiVital recording, verifies it, and embeds its exact samples into the deployed `index.html`. All analysis and simulations run locally in the browser. The website's **Save complete offline website** button saves an HTML copy containing the recording and all interactive code.

## What is included

- Published research results, with linked primary sources and explicit author-reported labels.
- A public-recording workbench: radar I/Q, range-time view, phase reconstruction, spectra, and comparison against a respiration belt.
- Four separately labeled simulations: phase sensitivity, spatial resolution, a sampling failure, and synthetic-map separability.
- Methods, limitations, validation plans, and source attribution.

The workbench is a teaching baseline, not a replication of the learned MobiVital method. One public recording is not population-level or clinical validation. The 62 GHz simulations are separate from the 7.29 GHz IR-UWB recording. The simulated map is not a measured lung-function image.

## Build and data provenance

`dataset.json` selects `231026_userI_tripod_01_5.csv` from the authors' [MobiVital repository](https://github.com/nesl/MobiVital-dataset). The production build:

1. Checks the dataset's explicit reuse terms using its linked Zenodo/DataCite metadata.
2. Resolves the source revision, downloads the CSV, and verifies its Git blob hash and byte count.
3. Validates exactly 1,500 rows × 254 finite numeric columns.
4. Embeds the unmodified CSV, SHA-256, source revision, license evidence, and attribution.
5. Rejects missing data, failed checks, or runtime data-fetch dependencies rather than substituting synthetic samples.

The deployed `data/manifest.json`, `data/license-evidence.json`, and `ATTRIBUTION.md` retain the provenance. Runtime connections are blocked by the page's content security policy; optional source links are for navigation only.

## Source layout and local build

The ordered `site/` fragments preserve the single-file website while keeping repository files manageable. `assemble_site.py` joins them into `index.template.html`; `build_site.py` prepares `_site/` for Pages.

```sh
python3 assemble_site.py
python3 -m unittest discover -s tests -v
python3 build_site.py
python3 tests/check_built_site.py _site/index.html
```

Python 3.10+ and Node.js are required for these commands; the build needs internet access to official data sources. Visitors do not need Python or Node. GitHub Actions supplies the build environment.

The packaging tests use explicitly synthetic software fixtures. Those fixtures are never published as human data. Passing software checks does not establish physiological accuracy.

## Publication boundary

This repository contains website source and build instructions, not a patient database or private credentials. A failed build means the complete site has not been published. Do not present an empty template as the completed public-data website.
