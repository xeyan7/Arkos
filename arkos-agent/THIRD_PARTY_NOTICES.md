# Third-party notices

This is the single index of third-party and inherited notices for the Arkos distribution.
Arkos-owned material is governed by the root [`LICENSE`](LICENSE)
(`SPDX-License-Identifier: LicenseRef-Arkos-Proprietary`). Nothing in this file revokes,
replaces, or restricts rights granted under the licenses of the components listed below.

The `Arkos distribution` value in bundled manifests identifies the product distribution, not
original copyright ownership.

## Inherited material — MIT License

Material inherited from earlier upstream projects is used under the MIT License. The notice is
preserved verbatim in [`licenses/inherited-MIT.txt`](licenses/inherited-MIT.txt) and applies to
the inherited portions of the components listed below.

```text
MIT License

Copyright (c) 2026 the copyright holders

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Inherited components covered by this notice:

- `optional-skills/software-development/ast-grep` — the upstream ast-grep skill. Its component
  copy of the same notice is at `optional-skills/software-development/ast-grep/LICENSE`.
- `skills/productivity/docx`, `skills/productivity/pdf`, `skills/productivity/powerpoint`,
  `skills/productivity/xlsx` — the upstream document skills these are built on.
- `skills/software-development/spike` — adapted from an external MIT-licensed spike workflow.

Arkos-owned additions, wiring, and modifications to these components remain subject to the
root `LICENSE`.

## Security guidance plugin — Apache License 2.0

`plugins/security-guidance/patterns.py` is a verbatim fork of an upstream security-patterns
file, including its unchanged regex/substring rule data. The fork is used under the Apache
License, Version 2.0:

- Full license text: [`plugins/security-guidance/LICENSE`](plugins/security-guidance/LICENSE)
- Attribution notice: [`plugins/security-guidance/NOTICE`](plugins/security-guidance/NOTICE)
- Source notice: the module docstring in `plugins/security-guidance/patterns.py`

The Arkos-side plugin glue code (`__init__.py`, `plugin.yaml`, `README.md`, tests) is original
work under the root `LICENSE`; importing the forked file does not change the license of either
file. Arkos modifications are limited to the module docstring and the removal of the upstream
RuleId telemetry table — the pattern data itself is unchanged.

Both files ship with every distribution that includes this plugin and must not be removed.

## First-party restatements

`skills/productivity/{docx,pdf,powerpoint,xlsx}/LICENSE` restate the root `LICENSE` for those
directories. They grant nothing beyond it and are not third-party notices.

## Notices that stay beside their component

These are part of the component's own source or template content. They are listed here so a
reader can find them, and they remain in force:

- Research paper templates: original copyright, bibliography, formatting, and licensing notices
  under `optional-skills/research/research-paper-writing/templates/`.
- SQLite vendor headers: the original notices in `native/fts5_cjk/vendor/sqlite3.h` and
  `native/fts5_cjk/vendor/sqlite3ext.h`.

## Names and identifiers

Provider names, service addresses, and external repository identifiers are required to
integrate with those services and do not identify the Arkos product's author.

## Scope

This index covers material bundled in this distribution. Arkos does not claim ownership of
third-party components and does not relicense them. Any distribution of this software must ship
this file, the root `LICENSE`, `licenses/inherited-MIT.txt`, and the component notices
referenced above.
