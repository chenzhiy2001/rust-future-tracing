from gdb_debugger.runtime_plugins.base import RuntimePlugin
from gdb_debugger.tracers.variable import VariableTracer
from gdb_debugger.tracers.backtrace import BacktraceTracer

# --- Tracer Factory Functions ---

def new_task_id_tracer():
    """Tracer for the raw u64 inside the tokio::task::Id newtype."""
    return VariableTracer("id.__0", scope='local')

def self_tracer():
    """Tracer for the raw pointer inside the RawTask struct."""
    return VariableTracer("self.ptr.pointer", scope='local')

def new_task_backtrace_tracer():
    """Backtrace tracer for RawTask::new to find the spawn location."""
    return BacktraceTracer()

def context_tracer():
    """Tracer for the static CONTEXT variable in Tokio."""
    return VariableTracer("CONTEXT", scope='static')


# --- Plugin Implementation ---

class TokioPlugin(RuntimePlugin):
    """A plugin to instrument the Tokio runtime."""

    @property
    def name(self):
        return "tokio"

    def instrument_points(self):
        """
        Defines breakpoints for key Tokio functions to trace task lifecycle events.
        """
        return [
            {
                "symbol": "tokio::runtime::task::raw::RawTask::new",
                "entry_tracers": [new_task_id_tracer, new_task_backtrace_tracer],
                "exit_tracers": [],
            },
            {
                "symbol": "tokio::runtime::task::raw::RawTask::poll",
                "entry_tracers": [self_tracer],
                "exit_tracers": [],
            },
            {
                "symbol": "tokio::runtime::task::raw::RawTask::shutdown",
                "entry_tracers": [self_tracer],
                "exit_tracers": [],
            },
            {
                "symbol": "tokio::runtime::task::raw::RawTask::dealloc",
                "entry_tracers": [self_tracer],
                "exit_tracers": [],
            },
        ]

    def process_data(self, all_traced_data: dict):
        """
        Prints a summary of the data collected from the Tokio runtime.
        """
        print("\n[gdb_debugger] ----- Tokio Runtime Data Report -----")
        for symbol, invocations in all_traced_data.items():
            print(f"\n  Symbol: {symbol} ({len(invocations)} calls)")
            for i, invocation in enumerate(invocations):
                print(f"    Invocation {i+1} (Thread {invocation['thread_id']}):")
                
                entry_data = invocation.get('entry_tracers', {})
                if entry_data:
                    print("      Entry Traces:")
                    for tracer, data in entry_data.items():
                        # Pretty print gdb.Value
                        if "gdb.Value" in str(type(data)):
                             data_str = str(data.lazy_string())
                        else:
                            data_str = str(data)
                        print(f"        - {tracer}: {data_str[:200]}")

                exit_data = invocation.get('exit_tracers', {})
                if exit_data:
                    print("      Exit Traces:")
                    for tracer, data in exit_data.items():
                        if "gdb.Value" in str(type(data)):
                             data_str = str(data.lazy_string())
                        else:
                            data_str = str(data)
                        print(f"        - {tracer}: {data_str[:200]}")

        print("\n[gdb_debugger] -------------------------------------\n")

# A single instance of the plugin to be loaded by the main script.
plugin = TokioPlugin() 