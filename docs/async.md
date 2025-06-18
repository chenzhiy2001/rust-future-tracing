## I want to reimplement BugStalker's async debugging capabilities using GDB Python Script, how do I do that

To reimplement BugStalker's async debugging capabilities using GDB Python scripts, you need to understand its core architecture and translate the key components. Here's how to approach it:
Core Architecture Overview

BugStalker's async debugging system consists of several key components that work together to provide runtime introspection of Tokio applications (src/debugger/async/mod.rs:37-56) . The system tracks async workers, blocked threads, and individual task backtraces.
1. Async Backtrace Collection

The main functionality revolves around building an AsyncBacktrace structure (src/debugger/async/mod.rs:152-205) . In GDB Python, you would:

    Use gdb.execute() to get thread information
    Parse Tokio's internal CONTEXT variable to extract task lists
    Analyze each thread to determine if it's a worker or blocked thread
    Build a comprehensive view of the runtime state

2. Tokio Version Detection

BugStalker supports multiple Tokio versions by parsing version strings from the binary's rodata section (src/debugger/async/tokio/mod.rs:28-48) . In GDB Python, you can:

    Use gdb.execute("info files") to find section addresses
    Read memory from the rodata section using gdb.selected_inferior().read_memory()
    Parse version strings to adapt to different Tokio internal structures

3. Task Extraction and Analysis

The most complex part is extracting individual tasks from Tokio's internal structures (src/debugger/async/tokio/task.rs:149-300) . This involves:

    Finding the task header pointer from Tokio's internal data structures
    Using the vtable to locate the poll function
    Extracting type information from DWARF debug data
    Casting raw pointers to the correct Cell<T, S> type
    Walking the future stack by following __awaitee fields

4. Async Stepping Implementation

BugStalker implements async-aware stepping by combining breakpoints and watchpoints (src/debugger/async/mod.rs:228-468) . In GDB Python:

    Set temporary breakpoints at statement boundaries within the current function
    Use hardware watchpoints on task state to detect completion
    Monitor the _task_context local variable to ensure you stay within the same task
    Handle task switching and completion detection

5. Oracle System for Runtime Monitoring

The oracle system uses transparent breakpoints on Tokio internal functions (src/oracle/builtin/tokio.rs:188-230) . In GDB Python:

    Set breakpoints on tokio::runtime::task::raw::RawTask::poll, new, and shutdown
    Use gdb.Breakpoint with Python callbacks
    Extract task information from function arguments
    Track task lifecycle events (creation, polling, completion)

6. Future Stack Walking

BugStalker walks the future stack by analyzing the __awaitee field in each future (src/debugger/async/tokio/task.rs:38-89) . In GDB Python:

    Use gdb.parse_and_eval() to access structure fields
    Handle different future types (AsyncFn, JoinHandle, Sleep, Custom)
    Recursively follow the chain of awaited futures
    Parse enum variants to determine future states

Key Challenges and Solutions

Memory Access: Use GDB's gdb.selected_inferior().read_memory() and pointer casting with gdb.parse_and_eval()

Type Information: Leverage GDB's type system with gdb.lookup_type() and structure field access

Async Context Tracking: Monitor the _task_context variable and task state flags to maintain debugging context

Tokio Internal Structures: Adapt to different Tokio versions by dynamically discovering structure layouts

Performance: Use hardware watchpoints sparingly due to CPU limitations (typically 4 watchpoints maximum) (src/debugger/async/mod.rs:86-90)
Implementation Strategy

Start by implementing the basic async backtrace collection, then add task extraction, and finally implement the stepping functionality. The oracle system can be added as an enhancement for runtime monitoring. Focus on supporting a single Tokio version initially, then extend to handle version differences.
Notes

BugStalker's async debugging is specifically designed for Tokio and requires deep knowledge of Tokio's internal structures. The implementation relies heavily on DWARF debugging information and direct memory access to the debugged process. When implementing in GDB Python, you'll need to handle the same low-level details while working within GDB's Python API constraints.

## Implementation Plan for GDB Python Script: BugStalker Async Debugging Capabilities
1. Core Architecture Design
AsyncBacktrace Structure

Implement a Python class equivalent to BugStalker's AsyncBacktrace structure (src/debugger/async/mod.rs:47-56) which contains workers, blocked threads, and tasks with their respective backtraces.
Main Async Debugging Interface

Create a main async debugging class similar to the debugger implementation (src/debugger/async/mod.rs:151-205) that coordinates all async debugging operations.
2. Tokio Version Detection
Version Extraction from Binary

Implement the naive version detection approach (src/debugger/async/tokio/mod.rs:31-48) by searching for "tokio-1." patterns in the rodata section of the binary. Use GDB's memory reading capabilities to scan loaded sections.
Version-Specific Adaptation

Create a version enumeration system (src/debugger/async/tokio/mod.rs:13-26) to handle different Tokio runtime versions and their varying internal structures.
3. Task Extraction and Analysis
Worker Detection

Implement worker thread detection logic (src/debugger/async/tokio/worker.rs:195-277) by:

    Analyzing thread backtraces for tokio worker patterns
    Extracting the CONTEXT global variable
    Identifying worker state (RunTask, Park, Unknown)

Task List Extraction

Create the owned task list extraction mechanism (src/debugger/async/tokio/worker.rs:282-383) by:

    Navigating the complex nested structure: CONTEXT.current.handle.value.__0.__0.data.shared.owned.list
    Walking linked lists of task headers
    Extracting task metadata and pointers

Task Header Analysis

Implement task analysis from headers (src/debugger/async/tokio/task.rs:151-300) by:

    Reading vtable information to identify poll functions
    Extracting task IDs and future information
    Parsing the Cell<T, S> type structure

4. Future Stack Walking
Future Chain Traversal

Implement the future stack walking algorithm (src/debugger/async/tokio/task.rs:38-89) by:

    Following __awaitee fields through the future chain
    Identifying different future types (AsyncFn, TokioSleep, JoinHandle, Custom)
    Building a complete future stack representation

Future State Parsing

Create future state analysis (src/debugger/async/future.rs:45-90) to extract:

    Suspend states with numeric identifiers
    Async function states (Unresumed, Returned, Panicked)
    Custom future type information

5. Async Stepping Implementation
Step Over with Task Tracking

Implement async step over functionality (src/debugger/async/mod.rs:235-468) using:

    Watchpoints on task completion flags
    Breakpoints on statement boundaries within functions
    Task context monitoring to ensure stepping within the same task

Step Out Implementation

Create step out functionality (src/debugger/async/mod.rs:500-594) by:

    Setting watchpoints on task state changes
    Waiting for task completion flags
    Handling interrupts and cleanup

Task State Monitoring

Implement task state tracking (src/debugger/async/tokio/task.rs:93-147) by reading atomic state values from task headers.
6. Oracle System for Runtime Monitoring
Transparent Breakpoint System

Create a breakpoint monitoring system (src/oracle/builtin/tokio.rs:188-230) that hooks into:

    tokio::runtime::task::raw::RawTask::poll for task polling events
    tokio::runtime::task::raw::RawTask::new for task creation
    tokio::runtime::task::raw::RawTask::dealloc and shutdown for task cleanup

Task Metrics Collection

Implement task metrics tracking (src/oracle/builtin/tokio.rs:67-137) including:

    Task creation timestamps
    Poll counts
    State transitions
    Task lifecycle management

Runtime Analysis

Create runtime state analysis (src/oracle/builtin/tokio.rs:303-349) for refreshing task states by reading memory and updating task information.
7. GDB Python Implementation Strategy
Memory Access Layer

Use GDB's Python API (gdb.parse_and_eval(), gdb.selected_inferior().read_memory()) to:

    Read complex nested structures
    Navigate pointer chains
    Access atomic variables and state fields

Symbol Resolution

Leverage GDB's symbol table access to:

    Find tokio runtime symbols
    Locate poll functions and task structures
    Resolve template type parameters

Breakpoint and Watchpoint Management

Utilize GDB's breakpoint API to:

    Set transparent breakpoints on key tokio functions
    Monitor task state changes with watchpoints
    Handle breakpoint events for oracle functionality

User Interface Integration

Create GDB commands that mirror BugStalker's async debugging interface, providing:

    Async backtrace display commands
    Task listing and analysis
    Async stepping commands
    Runtime monitoring output

Notes

This implementation plan leverages BugStalker's proven approach to async debugging while adapting it to GDB's Python scripting environment. The key challenge will be translating BugStalker's Rust-native memory access and type system navigation to GDB's Python interface, while maintaining the same level of detail and accuracy in async runtime analysis.