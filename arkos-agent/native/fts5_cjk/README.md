# fts5_cjk — cjk_unicode61 FTS5 tokenizer

unicode61 + CJK character bigrams (Lucene CJKAnalyzer semantics). Fixes
1-2 char Korean/Chinese/Japanese terms falling through to LIKE full-table
scans in session search.

Build & install to `~/.arkos/lib/`:

    ./build.sh

Uses the system `sqlite3ext.h` when available, else the vendored copy in
`vendor/` — no libsqlite3-dev required.

Once the extension is installed, the next `SessionDB` open creates the
`messages_fts_cjk` index (external-content, tool rows excluded — same v23
storage discipline as the other indexes). On a populated database, run

    arkos sessions optimize-storage

to backfill it; new messages are indexed live either way. Set
`sessions.cjk_fts: false` in `~/.arkos/config.yaml` to disable. Override
the .so location with `ARKOS_FTS5_CJK_SO`.

*Part of Arkos, an AI agent engine.*
