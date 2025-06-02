import sys, json, subprocess, re, os, pathlib
from typing import Dict

# Re-use the existing analyser without circular import problems
tool_root = pathlib.Path(__file__).resolve().parent
# sys.path.append(str(tool_root / 'src')) # No longer needed, main.py is in the same directory
# from main import DwarfAnalyzer # Changed to relative import
from .main import DwarfAnalyzer

_symbol_cache = None  # tuple(list_dems, list_mangled)


def _load_symbol_tables(binary: str):
    """Load symbol table once via objdump, returning list of (demangled,mangled)."""
    global _symbol_cache
    if _symbol_cache is not None:
        return _symbol_cache
    try:
        raw = subprocess.check_output(["objdump", "-t", binary], text=True)
        # demangle with rustfilt if available
        try:
            dem_raw = subprocess.check_output(["rustfilt"], input=raw, text=True)
        except Exception:
            dem_raw = raw  # fallback: no demangling
    except Exception:
        _symbol_cache = ([], [])
        return _symbol_cache
    demangled = []
    mangled = []
    raw_lines = raw.splitlines()
    dem_lines = dem_raw.splitlines()
    for raw_line, dem_line in zip(raw_lines, dem_lines):
        # We want all function symbols (local or global) in .text
        if " .text" not in raw_line:
            continue
        parts = raw_line.split()
        if len(parts) < 6:
            continue
        m_sym = parts[-1]
        # demangled substring starts at same column position
        idx = raw_line.find(m_sym)
        d_sym = dem_line[idx:].strip()
        mangled.append(m_sym)
        demangled.append(d_sym)
    _symbol_cache = (demangled, mangled)
    return _symbol_cache


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
        # We also need to handle `::{closure#0}` or `::{async_fn_env#0}` which DWARF gives directly
        if type_name_part.endswith(base_struct_name) or base_struct_name in type_name_part:
            if '{async_fn_env#' in base_struct_name and base_struct_name in type_name_part:
                 return mangled_sym
            elif '{async_block_env#' in base_struct_name and base_struct_name in type_name_part:
                 return mangled_sym
            elif type_name_part.endswith(base_struct_name) and '{async' not in base_struct_name: # Avoid generic structs named like async fns
                return mangled_sym

    return ""

def export(binary: str, out_json: str):
    analyzer = DwarfAnalyzer(binary)
    analyzer.parse_dwarf()
    future_map: Dict[str, Dict[str, str]] = {}
    for s in analyzer.structs.values():
        if not s.state_machine:
            continue
        key = f"0x{s.type_id}" if s.type_id else s.name
        future_map[key] = {
            "name": s.name,
            "poll_symbol": find_poll_symbol(binary, s.name)
        }
    with open(out_json, "w") as f:
        json.dump(future_map, f, indent=2)
    print(f"[+] exported {len(future_map)} futures to {out_json}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m future_analyzer.export_map <binary> <out.json>")
        sys.exit(1)
    export(sys.argv[1], sys.argv[2]) 