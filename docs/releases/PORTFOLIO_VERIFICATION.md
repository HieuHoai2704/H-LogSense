# H-logsen platform release verification

| Platform | Desktop renderer | CI verification |
| --- | --- | --- |
| Windows x64 | Edge WebView2 | Windows ZIP install, native window smoke, Chromium workbench scenarios |
| macOS Apple silicon and Intel | WKWebView | macOS ZIP install, native window smoke, Chromium workbench scenarios |
| Ubuntu 24.04 x64 | WebKitGTK | Linux ZIP install with system Python, native window smoke under Xvfb, Chromium workbench scenarios |

Run from a clean checkout with Python 3.10–3.13, or the system Python 3.14 on
Ubuntu 26.04. Use an empty output
directory for each build.

```text
python -m scripts.release.package_workbench --output dist/portfolio
python -m scripts.release.qa_portfolio_install dist/portfolio --desktop --report dist/portfolio/install.json
```

The verification checks the source and platform ZIP hashes, installs the wheel
from the download in a fresh environment, checks the installed CLI and API, and
runs the Python suite from the archived source. Linux uses the distribution's
system Python for GTK bindings. Its report records the platform, archive hashes,
resolved packages and desktop smoke result. Dependency ranges may resolve
differently in a later build.

[Workbench CI](../../.github/workflows/workbench-ci.yml) builds the archives
once and tests those exact files on the four runners. The final Actions artifact
`h-logsen-verified-release-assets` is available only after every matrix job
passes. The matrix tests the local workbench. Real MySQL verification and
manual desktop checks such as the native folder dialog have separate scope.

## Measurement scope

- [BGL/MySQL results](../database/IMPLEMENTATION_REPORT.md) document a real
  one-million parsed-log prefix on one Windows workstation. Import took
  294.710 s at 3,393.2 rows/s and 70.88 MiB importer peak RSS. Log Explorer
  p95 was 846.59 ms and its log-volume timeline p95 was 471.12 ms, across
  20 sequential warm loopback requests for each endpoint.
- [BGL July holdout](../ml/IF_JULY_HOLDOUT.md) documents the validation-selected
  experimental Isolation Forest with 22.52% precision, 55.43% recall,
  0.3203 F1, 0.2656 AP and 0.2037% FPR on 172,529 observed host-windows.
  This experiment measures one detector and one temporal cohort.
- Workbench browser tests verify live updates, terminal interaction and
  attachment correctness. Desktop responsiveness under sustained multi-run
  workloads requires a dedicated benchmark.

## Publication checklist

- Review the exact archive or commit selected for publication and scan its
  files and any public Git history for credentials or private paths and data.
- Preserve the [third-party notices](../../THIRD_PARTY_NOTICES.md). Keep BGL
  downloads, trained artifacts and paper PDFs outside the public bundle unless
  redistribution terms are verified for the intended use.
- Decide the first-party source license, record brand and icon provenance,
  and verify the app name for the intended market.
- Review platform results and the SHA-256 manifest for the selected version.
  Download the verified Actions artifact and attach the three platform ZIPs and
  the SHA-256 file to a draft GitHub Release. Link the exact tested commit and
  publish the draft after review. The source ZIP is optional.
