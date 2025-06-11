# Future Analyzer

A tool for analyzing Rust futures through DWARF debug information.

## Description

This tool analyzes Rust binaries to extract information about async functions and their state machines. It uses DWARF debug information to understand the structure of futures and their dependencies.

## Features

- Extracts async function structures
- Analyzes state machine layouts
- Shows memory layout of futures
- Identifies future dependencies

## Requirements

- Python 3.7+
- objdump (from binutils)

## Installation

1. Clone this repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Build your Rust program with debug information:
```bash
cargo build --release
```

2. Run the analyzer:
```bash
python src/main.py path/to/your/binary
```

## Example Output

```
=== Future Analysis ===

Async Functions:
{async_fn_env#0}:
  Size: 32 bytes
  Alignment: 4 bytes
  Members:
    __state:
      Type: <0xfb3>
      Offset: 12
      Size: 1
      Alignment: 1

State Machines:
{async_fn_env#0}:
  Size: 32 bytes
  Alignment: 4 bytes
  Members:
    __state:
      Type: <0xfb3>
      Offset: 12
      Size: 1
      Alignment: 1
```

## How It Works

The tool uses `objdump` to extract DWARF debug information from the binary. It then parses this information to:

1. Identify async function structures
2. Extract state machine information
3. Analyze memory layouts
4. Show future dependencies

## Technical Details: Identifying Async and Building Dependencies

This section details the precise rules used by the analyzer to identify async-related DWARF information and construct the future dependency tree.

### 1. Identifying Async-Related DWARF Information

A DWARF `DW_TAG_structure_type` entry is considered **async-related** based on its name.

**Rules:**

*   A structure is marked as an **`is_async_fn`** (representing an async function's environment) if its `DW_AT_name` attribute matches the regular expression `async_fn_env|async_block_env`.
*   A structure is marked as a **`state_machine`** (representing a future or part of a future's state) if:
    *   It is already an `is_async_fn`, OR
    *   Its `DW_AT_name` attribute matches the regular expression `Future|future` (case-insensitive).

**Relevant Code Snippet (`_parse_struct_block` method):**

```python
# ... inside _parse_struct_block method ...
        if name:
            is_async_fn = re.search(r'async_fn_env|async_block_env', name) is not None
            state_machine = is_async_fn or re.search(r'Future|future', name, re.IGNORECASE) is not None
# ...
            struct = Struct(
                name=unique_name,
                # ... other fields ...
                is_async_fn=is_async_fn,
                state_machine=state_machine,
                type_id=type_id
            )
            self.structs[unique_name] = struct
```

### 2. Building the Future Dependency Tree

The future dependency tree (`dependency_tree` in the JSON output) maps each `state_machine` structure to a list of other `state_machine` structures it directly or indirectly contains as members.

**Rules:**

1.  The process starts by iterating through all structures identified as `state_machine`.
2.  For each such `state_machine` (let's call it `S_parent`), a recursive search (`_resolve_deps_recursive`) is performed on its members:
    *   For each member `M` of `S_parent`:
        *   The type of `M` (given by `DW_AT_type`, which is a type ID like `<0x123ab>`) is resolved to its actual structure name using an internal mapping (`self.type_id_to_struct`). Let this be `S_child`.
        *   If `S_child` has already been visited in the current recursive path (to prevent cycles), it's skipped.
        *   If `S_child` itself is a `state_machine`, it is added as a direct dependency of `S_parent`.
        *   Regardless of whether `S_child` is a `state_machine` or not, the recursive search continues into `S_child`'s members. This allows the discovery of nested futures that might be wrapped within intermediate non-state-machine structures.
3.  The final `dependency_tree` stores each parent `state_machine` as a key, and its value is a list of all unique child `state_machine`s found through this recursive process.

**Relevant Code Snippets:**

**Main loop (`build_dependency_tree` method):**

```python
    def build_dependency_tree(self):
        """Build a dependency tree of futures/state machines, following nested structs recursively."""
        tree: Dict[str, List[str]] = {}
        for struct in self.structs.values():
            if not struct.state_machine: # Only start from known state machines
                continue
            # Initialize 'seen' set with the current struct to handle self-references if any
            deps = self._resolve_deps_recursive(struct, {struct.name})
            tree[struct.name] = list(deps)
        return tree
```

**Recursive resolution (`_resolve_deps_recursive` method):**

```python
    # Recursive helper to gather state-machine deps, walking through
    # intermediate non-state-machine structs.
    def _resolve_deps_recursive(self, struct: Struct, seen: Set[str]) -> Set[str]:
        deps: Set[str] = set()
        for mem in struct.members:
            if mem.type not in self.type_id_to_struct: # Check if member type ID is known
                continue
            child_name = self.type_id_to_struct[mem.type] # Resolve type ID to struct name
            if child_name in seen: # Avoid cycles and redundant processing
                continue
            seen.add(child_name) # Mark as visited for this path

            child_struct = self.structs.get(child_name)
            if not child_struct:
                continue

            if child_struct.state_machine: # If the child struct is a state machine, add it
                deps.add(child_name)
            
            # Whether state_machine or not, keep walking to discover nested futures
            # Pass the *updated* 'seen' set for the recursive call
            deps.update(self._resolve_deps_recursive(child_struct, seen))
        return deps
```

### 3. Mapping Future Names to Poll Function Symbols (`export_map.py`)

The `export_map.py` script is responsible for creating a JSON file (`future_map.json`) that maps a future's type ID (or name if ID is unavailable) to its properties, including the mangled name of its `poll` function. This mapping is crucial for runtime tools that might need to set breakpoints or gather information about future polling.

**Process:**

1.  **Load Symbol Tables:**
    *   The script executes `objdump -t <binary>` to retrieve the binary's symbol table.
    *   It attempts to demangle these symbols using `rustfilt` if the tool is present in the system's PATH. If `rustfilt` is not found, it proceeds with the mangled symbols.
    *   Both demangled (if available) and mangled symbol lists are cached to prevent redundant calls to `objdump` and `rustfilt` on subsequent lookups for the same binary.
    *   Only symbols located in the `.text` section (executable code) are considered.

2.  **Normalize DWARF Struct Name:**
    *   The struct name as identified by the DWARF analyzer (e.g., `tokio::time::sleep::Sleep<tokio::time::driver::Driver>`, or `main::{async_fn_env#0}`) needs to be compared against demangled symbol names.
    *   For this comparison, a `base_struct_name` is extracted from the DWARF name. This is typically the last component of the path, stripped of any generic parameters (e.g., `Sleep` from `tokio::time::sleep::Sleep<...>`).

3.  **Find Matching Poll Symbol:**
    *   The script iterates through all demangled symbols.
    *   It filters for symbols that represent `poll` functions. These are identified by looking for demangled names ending with `::poll`.
    *   For each candidate `poll` symbol, the script extracts the type name part that appears before `::poll` (or before ` as core::future::future::Future>::poll` if the full trait path is present).
    *   A match is determined based on the `base_struct_name` and the extracted `type_name_part` from the demangled symbol:
        *   If the `base_struct_name` (from DWARF) contains `async_fn_env#` or `async_block_env#` (indicating a compiler-generated async function environment), the script checks if this `base_struct_name` is *contained within* the `type_name_part` of the demangled poll symbol.
        *   For other struct names, it checks if the `type_name_part` *ends with* the `base_struct_name`. This helps distinguish `MyStruct::poll` from the poll function of a different future that might take `MyStruct` as a generic argument (e.g., `WrapperFuture<MyStruct>::poll`).
    *   If a matching demangled symbol is found, its corresponding *mangled* symbol name is considered the poll function for the DWARF struct. This mangled name is what's typically used by debuggers or profilers.
    *   If no match is found, the `poll_symbol` field in the output JSON will be an empty string.

**Relevant Code Snippet (`find_poll_symbol` function in `export_map.py`):**

```python
def find_poll_symbol(binary: str, struct_name: str) -> str:
    """Find the mangled poll symbol for a given struct by scanning demangled names."""
    demangled_names, mangled_names = _load_symbol_tables(binary)

    # Normalize the struct_name from DWARF to match the demangled format
    # e.g. "MyStruct<...blah...>" -> "MyStruct"
    base_struct_name = struct_name.split('<')[0].split('::')[-1]

    for demangled_sym, mangled_sym in zip(demangled_names, mangled_names):
        # Check if the demangled symbol is a poll function for the given struct
        # It should look like:  <path::to::MyStruct<...generics...> as core::future::Future>::poll
        # Or for closures:       <path::to::some_fn::{async_fn_env#0}>::poll
        if "::poll" not in demangled_sym:
            continue

        # Extract the part before " as core::future::Future>::poll" or just before "::poll"
        # This should be the struct/enum name with its path and generics
        type_name_part = ""
        if " as core::future::future::Future>::poll" in demangled_sym:
            type_name_part = demangled_sym.split(" as core::future::future::Future>::poll")[0]
        elif "::poll" in demangled_sym:
            type_name_part = demangled_sym.split("::poll")[0]

        # Check if the base_struct_name is part of the extracted type name
        # We check if the type_name_part *ends with* the base_struct_name to avoid
        # matching a struct that might be a parameter to the actual future.
        # e.g. SomeFuture<MyStruct> should not match MyStruct::poll
        # We also need to handle `{closure#0}` or `{async_fn_env#0}` which DWARF gives directly
        if type_name_part.endswith(base_struct_name) or base_struct_name in type_name_part:
            if '{async_fn_env#}' in base_struct_name and base_struct_name in type_name_part:
                 return mangled_sym
            elif '{async_block_env#}' in base_struct_name and base_struct_name in type_name_part:
                 return mangled_sym
            # Avoid generic structs named like async fns if base_struct_name itself doesn't indicate an async env
            elif type_name_part.endswith(base_struct_name) and '{async' not in base_struct_name:
                return mangled_sym
    return ""
```

## Contributing

Feel free to submit issues and enhancement requests! 

## Future Dependency Visualization

The tool includes a visualization module that generates interactive graphs of future dependencies using Graphviz DOT format.

### Requirements

Additional requirements for visualization:
- Graphviz (for generating static images)
- xdot (for interactive viewing)

Install on Ubuntu/Debian:
```bash
sudo apt-get install graphviz xdot
```

### Usage

1. First, generate the dependency JSON:
```bash
python dwarf_analyzer/main.py binary --json > results/async.json
```

2. Generate and view the dependency graph:
```bash
# Generate DOT file
python dwarf_analyzer/visualize_deps.py results/async.json

# View interactively (recommended for large graphs)
xdot results/async.dot

# Or generate a static image
dot -Tpng results/async.dot -o results/async.png
```

### Interactive Features (xdot)

When using xdot, you can:
- Search for nodes using Ctrl+F
- Zoom in/out
- Pan around
- Click and drag nodes to rearrange them
- Export to various formats

### Graph Features

- Left-to-right layout for better readability
- Monospace font for type names
- Light blue boxes for nodes
- Full type names as labels
- Searchable nodes
- Efficient rendering for large graphs (hundreds of nodes) 