import gdb
import os
import sys
import importlib

# --- Setup ---

# Add the project's root directory to Python's path to allow for absolute imports
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Determine which runtime plugin to use from environment variable or default
PLUGIN_NAME = os.getenv("GDB_DEBUGGER_PLUGIN", "tokio")


# --- Global Data Store ---

# A dictionary to hold all data collected by tracers.
# Structure: {
#   "symbol_name": [
#     {
#       "thread_id": gdb.Thread.ptid,
#       "entry_tracers": { "TracerClassName": data, ... },
#       "exit_tracers": { "TracerClassName": data, ... }
#     },
#     ...
#   ],
#   ...
# }
traced_data = {}

# This list holds temporary commands for breakpoints.
bp_commands = []

def run_tracers(symbol_name, entry_tracers, exit_tracers):
    """
    Called by the temporary breakpoint's command to run tracers
    after the function prolog has safely completed.
    """
    thread = gdb.selected_thread()
    if symbol_name not in traced_data:
        traced_data[symbol_name] = []
    
    invocation_data = {
        "thread_id": thread.ptid,
        "entry_tracers": {},
        "exit_tracers": {},
    }
    traced_data[symbol_name].append(invocation_data)

    for tracer_factory in entry_tracers:
        tracer = tracer_factory()
        tracer.start(thread)
        invocation_data["entry_tracers"][str(tracer)] = tracer.read_data()

    if exit_tracers:
        FinishBreakpoint(gdb.newest_frame(), symbol_name, invocation_data, exit_tracers)


# --- Load Plugin ---

try:
    # Use absolute path for robustness
    SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    
    PLUGIN_NAME = os.getenv("GDB_DEBUGGER_PLUGIN", "tokio")
    plugin_mod = importlib.import_module(f"gdb_debugger.runtime_plugins.{PLUGIN_NAME}")
    plugin = plugin_mod.plugin
    print(f"[gdb_debugger] Loaded runtime plugin: {plugin.name}")
except (ImportError, AttributeError) as e:
    print(f"[gdb_debugger] ERROR: Failed to load plugin '{PLUGIN_NAME}': {e}.")
    plugin = None


# --- Breakpoint Implementation ---

class FinishBreakpoint(gdb.FinishBreakpoint):
    """
    A finish breakpoint that runs tracers when a function call completes.
    """
    def __init__(self, frame: gdb.Frame, symbol_name: str, invocation_data: dict, exit_tracers: list):
        super().__init__(frame, internal=True)
        self.symbol_name = symbol_name
        self.invocation_data = invocation_data
        self.exit_tracers = exit_tracers

    def stop(self):
        """Called when the frame is about to return."""
        thread = gdb.selected_thread()
        for tracer_factory in self.exit_tracers:
            tracer = tracer_factory()
            tracer.start(thread)
            self.invocation_data["exit_tracers"][str(tracer)] = tracer.read_data()
        return False  # Always continue execution

    def out_of_scope(self):
        """Called when the frame is unwound, e.g., by an exception."""
        self.invocation_data["exit_tracers"]["error"] = "out_of_scope (e.g. exception)"


class EntryBreakpoint(gdb.Breakpoint):
    """
    A two-stage breakpoint to reliably trace function arguments by
    stepping over the function's prolog code.
    """
    def __init__(self, symbol: str, entry_tracers: list, exit_tracers: list):
        super().__init__(symbol, internal=True)
        self.symbol_name = symbol
        self.entry_tracers = entry_tracers
        self.exit_tracers = exit_tracers

    def stop(self):
        # This breakpoint hits at the raw function entry. We now set a
        # temporary breakpoint at the same spot to run our tracers.
        pc = gdb.selected_frame().pc()
        t_break = gdb.Breakpoint(f"*{pc}", gdb.BP_BREAKPOINT, internal=True, temporary=True)
        
        # We store the Python function to call in a global list and use its
        # index to call it from the breakpoint's command string.
        cmd_index = len(bp_commands)
        bp_commands.append(lambda: run_tracers(self.symbol_name, self.entry_tracers, self.exit_tracers))
        
        # The command string for the temporary breakpoint. It calls our Python
        # function, then tells GDB to continue automatically.
        t_break.commands = f"""
python bp_commands[{cmd_index}]()
continue
"""
        return False # Immediately continue to hit the temporary breakpoint.


# --- GDB Commands ---

class StartAsyncDebugger(gdb.Command):
    """GDB command to start the async debugger and set breakpoints."""
    def __init__(self):
        super().__init__("start-async-debug", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not plugin:
            print("[gdb_debugger] No plugin loaded. Cannot start.")
            return

        print("[gdb_debugger] Setting instrumentation points...")
        for point in plugin.instrument_points():
            try:
                EntryBreakpoint(point["symbol"], point["entry_tracers"], point["exit_tracers"])
                print(f"  - Breakpoint set for {point['symbol']}")
            except gdb.error as e:
                print(f"  - ERROR setting breakpoint for {point['symbol']}: {e}")
        
        print("\n[gdb_debugger] Instrumentation complete. Run your program.")
        print("Use 'dump-async-data' after execution to see the report.")

class DumpAsyncData(gdb.Command):
    """GDB command to process and dump the collected trace data."""
    def __init__(self):
        super().__init__("dump-async-data", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not plugin:
            print("[gdb_debugger] No plugin loaded.")
            return
        
        print("[gdb_debugger] Processing collected data...")
        plugin.process_data(traced_data)


# --- Register GDB Commands ---

if plugin:
    StartAsyncDebugger()
    DumpAsyncData()
else:
    print("[gdb_debugger] Commands not registered due to plugin load failure.") 