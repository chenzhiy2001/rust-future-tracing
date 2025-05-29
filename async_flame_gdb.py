import gdb, json, time, pathlib, importlib, sys, re, os

# Add script's directory to sys.path to find runtime_plugins
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

ROOT = SCRIPT_DIR # Assuming future_map.json is in the same dir as the script
MAP_FILE = ROOT / "future_map.json"
# PLUGIN_NAME = gdb.parameter("plugin") if hasattr(gdb, "parameter") else "tokio"  # default tokio
PLUGIN_NAME = os.getenv("ASYNC_FLAME_PLUGIN", "tokio")

# ---------- util -------------

def monotonic_ns():
    """Best effort monotonic ns using gdb call into inferior if possible."""
    try:
        val = gdb.parse_and_eval("(long long)clock_gettime_nsec_np(1)")
        return int(val)
    except gdb.error:
        return int(time.time() * 1e9)

trace_events = []

def emit(ph, ts, tid, name, args=None):
    ev = {
        "ph": ph,
        "ts": ts / 1000,  # chrome expects us below 1e9 (us)
        "pid": "1",
        "tid": str(tid),
        "name": name,
    }
    if args:
        ev["args"] = args
    trace_events.append(ev)

# ---------- load future map -------------
if not MAP_FILE.exists():
    print(f"[async-flame] ERROR: future_map.json not found at {MAP_FILE}")
    raise SystemExit
with MAP_FILE.open() as f:
    FUT_MAP = json.load(f)

# build poll symbol → display name lookup
symbol_to_name = {}
for meta in FUT_MAP.values():
    sym = meta.get("poll_symbol")
    if sym:
        symbol_to_name[sym] = meta["name"]

# ---------- load runtime plugin ----------
try:
    plugin_mod = importlib.import_module(f"runtime_plugins.{PLUGIN_NAME}")
    RuntimePluginCls = next(
        cls for cls in plugin_mod.__dict__.values()
        if isinstance(cls, type) and issubclass(cls, importlib.import_module("runtime_plugins.base").RuntimePlugin)
    )
    plugin = RuntimePluginCls()
except Exception as e:
    print(f"[async-flame] failed to load plugin {PLUGIN_NAME}: {e}")
    plugin = importlib.import_module("runtime_plugins.base").RuntimePlugin()

# ---------- breakpoints ------------
class PollBP(gdb.Breakpoint):
    def __init__(self, symbol, disp_name):
        super().__init__(symbol, internal=False)
        self.disp_name = disp_name
    def stop(self):
        tid = gdb.selected_thread().ptid[1]
        ts = monotonic_ns()
        emit("B", ts, tid, self.disp_name)
        gdb.execute("finish")
        emit("E", monotonic_ns(), tid, self.disp_name)
        return False

class PluginBP(gdb.Breakpoint):
    def __init__(self, symbol):
        super().__init__(symbol, internal=True)
        self.sym = symbol
    def stop(self):
        tid = gdb.selected_thread().ptid[1]
        ts = monotonic_ns()
        emit("i", ts, tid, self.sym, plugin.on_breakpoint(self.sym, gdb.selected_inferior()))
        return False

# set breakpoints
for sym, name in symbol_to_name.items():
    try:
        PollBP(sym, name)
    except gdb.error:
        pass
for sym in plugin.extra_breakpoints():
    try:
        PluginBP(sym)
    except gdb.error:
        pass

# command to dump json
class DumpTrace(gdb.Command):
    def __init__(self):
        super().__init__("dump_async_flame", gdb.COMMAND_USER)
    def invoke(self, arg, from_tty):
        out = {
            "traceEvents": trace_events,
            "displayTimeUnit": "ns"
        }
        with open("traceEvents.json", "w") as fp:
            json.dump(out, fp, indent=2)
        print("[async-flame] traceEvents.json written (events=", len(trace_events), ")")

DumpTrace()

print(f"[async-flame] breakpoints set → {len(symbol_to_name)} future polls, {len(plugin.extra_breakpoints())} runtime events") 