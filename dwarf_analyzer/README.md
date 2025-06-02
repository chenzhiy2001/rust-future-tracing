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

## Contributing

Feel free to submit issues and enhancement requests! 