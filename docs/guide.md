# Async-Flame Guide

This document walks you through generating a **future map**, collecting **async-poll traces** in GDB and visualising them in Chrome's built-in trace viewer.

---

## 0. Prerequisites

1. **Rust** (nightly toolchain recommended)
2. **GDB ≥ 9** _with Python support enabled_  
   On Ubuntu: `sudo apt install gdb` is usually enough.
3. **Python 3.8+** and the packages in `dwarf_analyzer/requirements.txt`  
   (Install with `pip install -r dwarf_analyzer/requirements.txt`).
4. For visualisation you only need a Chromium-based browser capable of loading a `traceEvents.json` file.

---

## 1. Build a Rust binary with DWARF symbols

The tools require full debuginfo so that DWARF contains all state-machine structs.

Example (`tests/tokio_test_project`):

```bash
cd tests/tokio_test_project
# ensure debug symbols even for --release
cargo build                       # debug build
# or: cargo build --release       # release build, debug=true is already set in Cargo.toml
```

The compiled binary will be located at
```
<workspace>/tests/tokio_test_project/target/debug/tokio_test_project
```
(or `.../release/` if you used `--release`).

---

## 2. Generate the **future map**

From the workspace root run:

```bash
python -m dwarf_analyzer.export_map \
  tests/tokio_test_project/target/debug/tokio_test_project \
  results/future_map.json
```

* `export_map.py` parses DWARF and tries to match every async state-machine to its
  `::poll` function symbol.  The result is written to `results/future_map.json`.

If the script prints **"exported 0 futures"** you likely pointed it at a binary
that was stripped or failed to build with debuginfo.

---

## 3. Record async-polls with GDB

```bash
gdb -q \
  --command=gdb_profiler/async_flame_gdb.py \
  --args tests/tokio_test_project/target/debug/tokio_test_project
```

Inside GDB:

```gdb
(gdb) run          # starts the program; breakpoints are silent
# … let the program finish or interrupt when you're done …
(gdb) dump_async_flame   # writes results/traceEvents.json
(gdb) quit
```

Environment variable `ASYNC_FLAME_PLUGIN` selects a runtime plugin
(currently only `tokio` is shipped). If unset, `tokio` is the default.

---

## 4. Visualizing the Future Dependency Graph

To better understand the relationships between futures, you can generate and visualize a dependency graph.

**1. Generate the Dependency JSON**

First, run the `dwarf_analyzer` to produce a JSON file containing the dependency tree:
```bash
python3 -m dwarf_analyzer.main tests/tokio_test_project/target/debug/tokio_test_project --json > results/async_dependencies.json
```

**2. Generate the DOT Graph File**

Next, use the `visualize_deps.py` script to convert the JSON into a DOT file:
```bash
python3 -m dwarf_analyzer.visualize_deps results/async_dependencies.json
```
This will create `results/async_dependencies.dot`.

**3. View the Graph**

You can now visualize the graph. For large graphs, interactive viewing with `xdot` is recommended.

*   **Interactive (with search):**
    ```bash
    xdot results/async_dependencies.dot
    ```
*   **Static Image (PNG):**
    ```bash
    dot -Tpng results/async_dependencies.dot -o results/dependency_graph.png
    ```

## 5. Generating and Visualizing a Flame Graph

1. Open Chrome/Chromium.
2. Navigate to `chrome://tracing` (or `about://tracing` in recent versions).
3. Click "Load" and select `results/traceEvents.json`.

You can now explore when each future's `poll` began and ended, grouped by OS
thread (`tid`).

---

## 6. Directory Layout

```
future-tracing/
│
├── dwarf_analyzer/      # DWARF parsing + future-map exporter
├── gdb_profiler/        # GDB Python script + runtime plugins
├── tests/               # Minimal async examples & larger Tokio demo
├── results/             # Generated artefacts (future_map.json, traceEvents.json)
└── docs/                # This guide and other documentation
```

---

## 7. Troubleshooting

* **`future_map.json not found` in GDB** – run step 2 first.
* **Zero futures exported** – rebuild your binary with debuginfo and confirm the path.
* **GDB shows fewer breakpoints than expected** – many state machines share the same
  compiled `poll` function; duplicates collapse to one breakpoint.
* **Plugin import error** – ensure `gdb_profiler` is on `PYTHONPATH` _or_ use absolute paths when invoking GDB.

Feel free to extend this guide as the tooling evolves. 