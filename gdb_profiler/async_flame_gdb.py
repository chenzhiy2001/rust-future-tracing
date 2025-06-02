import gdb, json, time, pathlib, importlib, sys, re, os

# Determine workspace root. Assumes this script is in a subdirectory of the workspace.
# When packaged, __file__ will be <workspace>/gdb_profiler/async_flame_gdb.py
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent # Goes up one level from gdb_profiler to future-tracing

MAP_FILE = WORKSPACE_ROOT / "results" / "future_map.json"
# PLUGIN_NAME = gdb.parameter("plugin") if hasattr(gdb, "parameter") else "tokio"  # default tokio
PLUGIN_NAME = os.getenv("ASYNC_FLAME_PLUGIN", "tokio")

# ---------- util -------------

def monotonic_ns():
    """Best effort monotonic ns using gdb call into inferior if possible."""
    try:
        # Try CLOCK_MONOTONIC_RAW first for robustness against time adjustments
        val_str = gdb.execute("call (long long)clock_gettime(CLOCK_MONOTONIC_RAW, {{&{struct timespec}ts, 0}}) == 0 ? (ts.tv_sec * 1000000000LL + ts.tv_nsec) : -1LL", to_string=True)
        val = int(val_str.split('=')[-1].strip())
        if val != -1:
            return val
        # Fallback to CLOCK_MONOTONIC if RAW is not available (e.g. older kernels/qemu)
        val_str = gdb.execute("call (long long)clock_gettime(CLOCK_MONOTONIC, {{&{struct timespec}ts, 0}}) == 0 ? (ts.tv_sec * 1000000000LL + ts.tv_nsec) : -1LL", to_string=True)
        val = int(val_str.split('=')[-1].strip())
        if val != -1:
            return val
    except gdb.error:
        pass # GDB error, fallback to host time
    return int(time.time() * 1e9) # Fallback to host time if gdb calls fail

trace_events = []

def emit(ph, ts_ns, tid, name, args=None, cat="future_poll"):
    ev = {
        "ph": ph,
        "ts": ts_ns / 1000,  # Chrome expects microseconds
        "pid": 1, # Use a single process ID for simplicity in visualization
        "tid": str(tid),
        "name": name,
        "cat": cat,
    }
    if args:
        ev["args"] = args
    trace_events.append(ev)

# ---------- load future map -------------
if not MAP_FILE.exists():
    # Try to guide the user if the map file is missing.
    expected_binary_path = WORKSPACE_ROOT / "tests" / "tokio_test_project" / "target" / "debug" / "tokio_test_project"
    export_script_path = WORKSPACE_ROOT / "dwarf_analyzer" / "export_map.py"
    print(f"[async-flame] ERROR: future_map.json not found at {MAP_FILE}.")
    print(f"[async-flame] Please generate it first. Example command:")
    print(f"[async-flame]   python {export_script_path} {expected_binary_path} {MAP_FILE}")
    FUT_MAP = {}
else:
    with MAP_FILE.open() as f:
        FUT_MAP = json.load(f)

symbol_to_name = {}
for meta in FUT_MAP.values():
    sym = meta.get("poll_symbol")
    if sym:
        # Ensure we use the DWARF name if available, otherwise fallback to mangled symbol name
        display_name = meta.get("name", sym) 
        symbol_to_name[sym] = display_name

# ---------- load runtime plugin ----------
try:
    plugin_mod_path = f"runtime_plugins.{PLUGIN_NAME}" # Relative to this file's new location
    base_plugin_mod_path = "runtime_plugins.base"

    # Ensure GDB can find the plugin directory (gdb_profiler/runtime_plugins)
    # The 'gdb_profiler' directory itself needs to be on sys.path for 'import runtime_plugins' to work
    # if this script is not run with `python -m gdb_profiler.async_flame_gdb`
    # SCRIPT_DIR is <workspace>/gdb_profiler
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
        
    plugin_mod = importlib.import_module(plugin_mod_path)
    RuntimePluginCls = next(
        cls for cls in plugin_mod.__dict__.values()
        if isinstance(cls, type) and issubclass(cls, importlib.import_module(base_plugin_mod_path).RuntimePlugin) and cls.__name__ != "RuntimePlugin"
    )
    plugin = RuntimePluginCls()
    print(f"[async-flame] Loaded runtime plugin: {plugin.name} from {plugin_mod.__file__}")
except Exception as e:
    print(f"[async-flame] Failed to load plugin '{PLUGIN_NAME}': {e}. Using generic plugin.")
    # Ensure base_plugin_mod_path is also findable if the initial import failed early
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    plugin = importlib.import_module(f"{base_plugin_mod_path}").RuntimePlugin() # Ensure full path for base

# ---------- breakpoints using FinishBreakpoint pattern ------------

# Stores entry metadata for finish breakpoints
# Key: gdb.Frame.id(), Value: dict {ts, name, tid}
finish_bp_metadata = {}

class PollFinishBP(gdb.FinishBreakpoint):
    def __init__(self, frame_id, name, entry_ts, tid):
        super().__init__(gdb.newest_frame(), internal=True)
        self.frame_id = frame_id
        self.name = name
        self.entry_ts = entry_ts
        self.tid = tid

    def stop(self):
        emit("E", monotonic_ns(), self.tid, self.name, cat="future_poll")
        if self.frame_id in finish_bp_metadata: # Clean up
            del finish_bp_metadata[self.frame_id]
        return False # Do not stop execution

    def out_of_scope(self):
        # Function exited via an exception or other non-standard path
        emit("E", monotonic_ns(), self.tid, f"{self.name} (unwound)", cat="future_poll_unwind")
        if self.frame_id in finish_bp_metadata: # Clean up
            del finish_bp_metadata[self.frame_id]

class PollBP(gdb.Breakpoint):
    def __init__(self, symbol, disp_name):
        super().__init__(symbol, internal=False) # User-visible breakpoint
        self.disp_name = disp_name

    def stop(self):
        try:
            tid = gdb.selected_thread().ptid[1]
            entry_ts = monotonic_ns()

            # Get unique ID for the current frame
            frame = gdb.newest_frame()
            # Use a robust method to obtain a unique identifier for the frame without relying on Frame.sp()
            try:
                sp_val = int(frame.read_register("sp"))
            except Exception:
                sp_val = 0

            frame_id = (frame.pc(), sp_val)

            # Store metadata for the finish breakpoint
            finish_bp_metadata[frame_id] = {
                'name': self.disp_name,
                'entry_ts': entry_ts,
                'tid': tid
            }

            emit("B", entry_ts, tid, self.disp_name, cat="future_poll")
            PollFinishBP(frame_id, self.disp_name, entry_ts, tid)  # Create finish breakpoint
        except Exception as e:
            # Ensure tracing keeps going even if something went wrong
            print(f"[async-flame] PollBP.stop error for {self.disp_name}: {e}")
        # Always continue execution
        return False

class PluginBP(gdb.Breakpoint):
    def __init__(self, symbol):
        super().__init__(symbol, internal=True)
        self.sym = symbol
    def stop(self):
        tid = gdb.selected_thread().ptid[1]
        ts = monotonic_ns()
        args = plugin.on_breakpoint(self.sym, gdb.selected_inferior())
        emit("i", ts, tid, self.sym, args=args, cat=f"plugin_{plugin.name}")
        return False

# set breakpoints
active_poll_bps = 0
for sym, name in symbol_to_name.items():
    if not sym: # Skip if poll_symbol was not found
        continue
    try:
        PollBP(sym, name)
        active_poll_bps += 1
    except gdb.error as e:
        print(f"[async-flame] Error setting PollBP for {name} ({sym}): {e}")
        pass # Continue if a symbol can't be resolved

active_plugin_bps = 0
for sym in plugin.extra_breakpoints():
    try:
        PluginBP(sym)
        active_plugin_bps +=1
    except gdb.error as e:
        print(f"[async-flame] Error setting PluginBP for {sym}: {e}")
        pass

# command to dump json
class DumpTrace(gdb.Command):
    def __init__(self):
        super().__init__("dump_async_flame", gdb.COMMAND_USER)
    def invoke(self, arg, from_tty):
        out_file_name = "traceEvents.json"
        if arg:
            out_file_name = arg.strip()
        
        # Ensure the output directory exists
        output_dir = WORKSPACE_ROOT / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_out_path = output_dir / out_file_name
            
        # Complete any pending finish breakpoints if the program has exited
        # This is a heuristic: if inferior is not valid, assume exit
        if not gdb.selected_inferior().is_valid():
            for frame_id, meta in list(finish_bp_metadata.items()): # list() for safe iteration
                emit("E", monotonic_ns(), meta['tid'], f"{meta['name']} (prog_exit)", cat="future_poll_exit")
                del finish_bp_metadata[frame_id]

        trace_payload = {
            "traceEvents": trace_events,
            "displayTimeUnit": "us" # Chrome prefers us
        }
        with open(final_out_path, "w") as fp:
            json.dump(trace_payload, fp, indent=2)
        print(f"[async-flame] {final_out_path} written (events={len(trace_events)})")

DumpTrace()

print(f"[async-flame] Breakpoints set: {active_poll_bps} future polls, {active_plugin_bps} runtime events from plugin '{plugin.name}'.")
print(f"[async-flame] Run your program. Then use 'dump_async_flame' to write traceEvents.json.") 