#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
import json
import os

@dataclass
class StructMember:
    name: str
    type: str
    offset: int
    size: int
    alignment: int
    is_artificial: bool = False
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None

@dataclass
class Struct:
    name: str
    size: int
    alignment: int
    members: List[StructMember]
    is_async_fn: bool
    state_machine: bool
    type_id: Optional[str] = None
    locations: List[Dict[str, any]] = field(default_factory=list)

class DwarfAnalyzer:
    def __init__(self, binary_path: str):
        self.binary_path = binary_path
        self.structs: Dict[str, Struct] = {}
        self.current_struct: Optional[Struct] = None
        self.current_member: Optional[StructMember] = None
        self.type_id_to_struct: Dict[str, str] = {}
        self.struct_name_to_type_id: Dict[str, str] = {}
        self.file_table: Dict[str, str] = {}

    def run_objdump(self) -> str:
        """Run objdump and return its output."""
        result = subprocess.run(['objdump', '--dwarf=info', self.binary_path], 
                              capture_output=True, text=True)
        return result.stdout

    def parse_dwarf(self):
        """Parse DWARF information from objdump output (robust block detection)."""
        output = self.run_objdump()
        lines = output.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            # First, look for the file table in a compile unit
            if 'DW_TAG_compile_unit' in line:
                self.file_table = {} # Reset for new compile unit
                comp_unit_lines = [line]
                i += 1
                while i < len(lines) and 'DW_TAG_compile_unit' not in lines[i]:
                    comp_unit_lines.append(lines[i])
                    i += 1
                self._parse_file_table(comp_unit_lines)
                # Restart parsing from the beginning of this unit for structs
                i -= len(comp_unit_lines)

            # Detect the beginning of a structure DIE – rely on depth value instead of spaces
            m = re.match(r'\s*<(\d+)><[0-9a-f]+>: Abbrev Number: .*?\(DW_TAG_structure_type\)', line)
            if m:
                struct_depth = int(m.group(1))
                struct_lines = [line]
                i += 1
                # Collect every subsequent line **until** we meet another DIE header ("Abbrev Number:")
                # whose depth is **less than or equal** to the current struct's depth.
                while i < len(lines):
                    l = lines[i]
                    m2 = re.match(r'\s*<(\d+)><[0-9a-f]+>: Abbrev Number:', l)
                    if m2:
                        depth = int(m2.group(1))
                        if depth <= struct_depth:
                            break
                    struct_lines.append(l)
                    i += 1
                self._parse_struct_block(struct_lines)
                continue
            i += 1

    def _parse_file_table(self, comp_unit_lines):
        """
        Parses the file table from a DWARF compilation unit.
        The file table is a list of file entries that follow the main CU attributes.
        """
        comp_dir = ""
        # First, find the compilation directory.
        for line in comp_unit_lines:
            if 'DW_AT_comp_dir' in line:
                match = re.search(r'DW_AT_comp_dir\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if match:
                    comp_dir = match.group(1).strip().strip('"') # Remove quotes if present
                    break
        
        # Now find file entries. In objdump output, these appear sequentially
        # and are not always explicitly tagged with DW_TAG_file_type on the same line.
        # This is a robust heuristic that assumes the file list starts after the main CU attributes.
        file_index = 1
        found_main_cu_name = False
        for line in comp_unit_lines:
            if 'DW_AT_name' in line:
                match = re.search(r'DW_AT_name\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if match:
                    name = match.group(1).strip()
                    if not found_main_cu_name:
                        # The first name is the compilation unit itself, skip it.
                        found_main_cu_name = True
                        continue
                    
                    # Subsequent names are file paths.
                    # This logic assumes they appear in order of their index.
                    full_path = os.path.join(comp_dir, name) if comp_dir and not os.path.isabs(name) else name
                    self.file_table[str(file_index)] = full_path
                    file_index += 1

    def _parse_struct_block(self, struct_lines):
        """Parse a block of lines describing a struct and its members."""
        name = None
        size = 0
        alignment = 0
        type_id = None
        is_async_fn = False
        state_machine = False
        members = []
        # Extract the DIE offset (type_id) from the header line – the second number inside "< >"
        m = re.search(r'<[0-9a-f]+><([0-9a-f]+)>', struct_lines[0].lstrip())
        if m:
            type_id = m.group(1)
        for idx, line in enumerate(struct_lines):
            if 'DW_AT_name' in line and name is None:
                name_match = re.search(r'DW_AT_name\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if name_match:
                    name = name_match.group(1).strip()
            if 'DW_AT_byte_size' in line:
                size_match = re.search(r'DW_AT_byte_size\s*:\s*(\d+)', line)
                if size_match:
                    size = int(size_match.group(1))
            if 'DW_AT_alignment' in line:
                align_match = re.search(r'DW_AT_alignment\s*:\s*(\d+)', line)
                if align_match:
                    alignment = int(align_match.group(1))
        if name:
            is_async_fn = re.search(r'async_fn_env|async_block_env', name) is not None
            state_machine = is_async_fn or re.search(r'Future|future', name, re.IGNORECASE) is not None
        # Now parse members
        member_block = []
        in_member = False
        for line in struct_lines:
            if 'DW_TAG_member' in line:
                if in_member and member_block:
                    member = self._parse_member_block(member_block)
                    if member:
                        members.append(member)
                    member_block = []
                in_member = True
            if in_member:
                member_block.append(line)
        if in_member and member_block:
            member = self._parse_member_block(member_block)
            if member:
                members.append(member)
        # Register struct – ensure unique key per type_id
        if name:
            unique_name = name
            if name in self.structs and type_id:
                unique_name = f"{name}<0x{type_id}>"
            struct = Struct(
                name=unique_name,
                size=size,
                alignment=alignment,
                members=members,
                is_async_fn=is_async_fn,
                state_machine=state_machine,
                type_id=type_id
            )
            self.structs[unique_name] = struct
            if type_id:
                self.type_id_to_struct[type_id] = unique_name
                self.struct_name_to_type_id[unique_name] = type_id

    def _parse_member_block(self, member_lines):
        name = None
        type_str = 'unknown'
        offset = 0
        alignment = 0
        is_artificial = False
        decl_file = None
        decl_line = None
        for line in member_lines:
            if 'DW_AT_name' in line and name is None:
                name_match = re.search(r'DW_AT_name\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if name_match:
                    name = name_match.group(1)
            if 'DW_AT_decl_file' in line:
                # First, try to resolve by file index (the robust method)
                file_index_match = re.search(r'DW_AT_decl_file\s*:\s*(\d+)', line)
                if file_index_match:
                    file_index = file_index_match.group(1)
                    decl_file = self.file_table.get(file_index, f"file_index_{file_index}")
                else:
                    # Fallback: try to parse it as a direct string (the heuristic)
                    file_name_match = re.search(r'DW_AT_decl_file\s*:\s*\d+\s+\d+\s+(.+)', line)
                    if file_name_match:
                        decl_file = file_name_match.group(1).strip()
            if 'DW_AT_decl_line' in line:
                line_match = re.search(r'DW_AT_decl_line\s*:\s*(\d+)', line)
                if line_match:
                    decl_line = int(line_match.group(1))
            if 'DW_AT_type' in line:
                type_match = re.search(r'DW_AT_type\s*:\s*<0x([0-9a-f]+)>', line)
                if type_match:
                    type_str = type_match.group(1)
            if 'DW_AT_data_member_location' in line:
                offset_match = re.search(r'DW_AT_data_member_location\s*:\s*(\d+)', line)
                if offset_match:
                    offset = int(offset_match.group(1))
            if 'DW_AT_alignment' in line:
                align_match = re.search(r'DW_AT_alignment\s*:\s*(\d+)', line)
                if align_match:
                    alignment = int(align_match.group(1))
            if 'DW_AT_artificial' in line:
                is_artificial = True
        if name is not None:
            return StructMember(
                name=name,
                type=type_str,
                offset=offset,
                size=0,  # Will be set later
                alignment=alignment,
                is_artificial=is_artificial,
                decl_file=decl_file,
                decl_line=decl_line
            )
        return None

    def analyze_futures(self):
        """Analyze future-related structures."""
        self.parse_dwarf()
        
        # Find all async function structures
        async_structs = {name: struct for name, struct in self.structs.items() 
                        if struct.is_async_fn}
        
        # Find all state machines
        state_machines = {name: struct for name, struct in self.structs.items() 
                         if struct.state_machine}
        
        return {
            'async_functions': async_structs,
            'state_machines': state_machines
        }

    def print_analysis(self):
        """Print the analysis results in a readable format."""
        analysis = self.analyze_futures()
        
        print("=== Future Analysis ===\n")
        
        print("Async Functions:")
        for name, struct in analysis['async_functions'].items():
            print(f"\n{name}:")
            print(f"  Size: {struct.size} bytes")
            print(f"  Alignment: {struct.alignment} bytes")
            print("  Members:")
            for member in struct.members:
                print(f"    {member.name}:")
                print(f"      Type: {member.type}")
                print(f"      Offset: {member.offset}")
                print(f"      Size: {member.size}")
                print(f"      Alignment: {member.alignment}")
                if member.is_artificial:
                    print(f"      Artificial: Yes")
        
        print("\nState Machines:")
        for name, struct in analysis['state_machines'].items():
            print(f"\n{name}:")
            print(f"  Size: {struct.size} bytes")
            print(f"  Alignment: {struct.alignment} bytes")
            print("  Members:")
            for member in struct.members:
                print(f"    {member.name}:")
                print(f"      Type: {member.type}")
                print(f"      Offset: {member.offset}")
                print(f"      Size: {member.size}")
                print(f"      Alignment: {member.alignment}")
                if member.is_artificial:
                    print(f"      Artificial: Yes")

    # Recursive helper to gather state-machine deps, walking through
    # intermediate non-state-machine structs.
    def _resolve_deps_recursive(self, struct: Struct, seen: Set[str]) -> Set[str]:
        deps: Set[str] = set()
        for mem in struct.members:
            if mem.type not in self.type_id_to_struct:
                continue
            child_name = self.type_id_to_struct[mem.type]
            if child_name in seen:
                continue
            seen.add(child_name)
            child_struct = self.structs.get(child_name)
            if not child_struct:
                continue
            if child_struct.state_machine:
                deps.add(child_name)
            # Whether state_machine or not, keep walking to discover nested futures
            deps.update(self._resolve_deps_recursive(child_struct, seen))
        return deps

    def build_dependency_tree(self):
        """Build a dependency tree of futures/state machines, following nested structs recursively."""
        tree: Dict[str, List[str]] = {}
        for struct in self.structs.values():
            if not struct.state_machine:
                continue
            deps = self._resolve_deps_recursive(struct, {struct.name})
            tree[struct.name] = list(deps)
        return tree

    def print_dependency_tree(self):
        tree = self.build_dependency_tree()
        print("\nFuture Dependency Tree:")
        def print_tree(name, level=0, visited=None):
            if visited is None:
                visited = set()
            print("  " * level + f"- {name}")
            visited.add(name)
            for dep in tree.get(name, []):
                if dep not in visited:
                    print_tree(dep, level+1, visited)
        # Print roots (state machines not contained by others)
        roots = set(tree.keys()) - {dep for deps in tree.values() for dep in deps}
        for root in roots:
            print_tree(root)

    def print_all_structs(self):
        print("\n[DEBUG] All parsed structures:")
        for name, struct in self.structs.items():
            print(f"  {name}: size={struct.size}, alignment={struct.alignment}, is_async_fn={struct.is_async_fn}, state_machine={struct.state_machine}")

    def output_json(self):
        analysis = self.analyze_futures()
        dep_tree = self.build_dependency_tree()
        def struct_to_dict(struct):
            locations = []
            for member in struct.members:
                if member.decl_file and member.decl_line:
                    locations.append({'file': member.decl_file, 'line': member.decl_line})
            
            return {
                'name': struct.name,
                'size': struct.size,
                'alignment': struct.alignment,
                'is_async_fn': struct.is_async_fn,
                'state_machine': struct.state_machine,
                'locations': locations,
                'members': [
                    {
                        'name': m.name,
                        'type': m.type,
                        'offset': m.offset,
                        'size': m.size,
                        'alignment': m.alignment,
                        'is_artificial': m.is_artificial,
                        'decl_file': m.decl_file,
                        'decl_line': m.decl_line
                    } for m in struct.members
                ],
                'type_id': struct.type_id
            }
        out = {
            'async_functions': [struct_to_dict(s) for s in analysis['async_functions'].values()],
            'state_machines': [struct_to_dict(s) for s in analysis['state_machines'].values()],
            'dependency_tree': dep_tree
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python main.py <binary_path> [--json]")
        sys.exit(1)
    binary_path = sys.argv[1]
    output_json = len(sys.argv) > 2 and sys.argv[2] == '--json'
    analyzer = DwarfAnalyzer(binary_path)
    if output_json:
        analyzer.output_json()
    else:
        analyzer.parse_dwarf()
        analyzer.print_all_structs()  # DEBUG: print all parsed structs
        analyzer.print_analysis()
        analyzer.print_dependency_tree()

if __name__ == "__main__":
    main() 