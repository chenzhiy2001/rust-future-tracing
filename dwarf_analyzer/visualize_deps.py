#!/usr/bin/env python3

import json
import sys
import os
from typing import Dict, List, Set
import re

def sanitize_node_name(name: str) -> str:
    """Convert a type name to a valid DOT node name."""
    # Replace special characters with underscores
    sanitized = re.sub(r'[<>(),: +\[\]]', '_', name)
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Ensure the name starts with a letter (DOT requirement)
    if not sanitized[0].isalpha():
        sanitized = 'n' + sanitized
    return sanitized

def create_dot_graph(dependency_tree: Dict[str, List[str]]) -> str:
    """Convert dependency tree to DOT format."""
    dot_lines = [
        'digraph FutureDependencies {',
        '    rankdir=LR;',  # Left to right layout
        '    node [shape=box, style=filled, fillcolor=lightblue, fontname="monospace"];',
        '    edge [fontname="monospace"];',
        '    // Node definitions',
    ]
    
    # Add nodes with their full type names as labels
    for future_type in dependency_tree:
        node_name = sanitize_node_name(future_type)
        # Escape quotes and backslashes in the label
        escaped_label = future_type.replace('\\', '\\\\').replace('"', '\\"')
        dot_lines.append(f'    "{node_name}" [label="{escaped_label}"];')
    
    # Add edges
    dot_lines.append('    // Edges')
    for future_type, deps in dependency_tree.items():
        source = sanitize_node_name(future_type)
        for dep in deps:
            target = sanitize_node_name(dep)
            dot_lines.append(f'    "{source}" -> "{target}";')
    
    dot_lines.append('}')
    return '\n'.join(dot_lines)

def main():
    if len(sys.argv) != 2:
        print("Usage: python visualize_deps.py <path_to_async.json>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    if not os.path.exists(json_path):
        print(f"Error: File {json_path} does not exist")
        sys.exit(1)
    
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        if 'dependency_tree' not in data:
            print("Error: No dependency_tree found in the JSON file")
            sys.exit(1)
        
        dot_content = create_dot_graph(data['dependency_tree'])
        
        # Write DOT file
        dot_path = os.path.splitext(json_path)[0] + '.dot'
        with open(dot_path, 'w') as f:
            f.write(dot_content)
        
        print(f"DOT file generated: {dot_path}")
        print("\nTo visualize the graph, you can use Graphviz:")
        print(f"dot -Tpng {dot_path} -o {os.path.splitext(dot_path)[0]}.png")
        print("\nFor interactive viewing with search capability, use xdot:")
        print(f"xdot {dot_path}")
        
    except json.JSONDecodeError:
        print("Error: Invalid JSON file")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 