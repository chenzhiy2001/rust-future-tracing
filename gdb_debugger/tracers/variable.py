from gdb_debugger.tracers.base import Tracer
import gdb
import struct

class VariableTracer(Tracer):
    """
    A tracer that reads a variable's value from the specified scope
    using a hybrid, robust approach.
    """
    def __init__(self, variable_name: str, scope: str = 'local'):
        """
        Initializes the tracer.
        `scope` can be 'local' (for local variables and arguments) or 'static'.
        """
        super().__init__()
        self.variable_name = variable_name
        self.scope = scope

    def start(self, inferior_thread: gdb.Thread):
        """
        Reads the variable's value using a hybrid strategy:
        1. Try a non-intrusive memory read first.
        2. If that fails, fall back to the powerful (but intrusive)
           gdb.parse_and_eval(), which can read from registers.
        """
        try:
            inferior_thread.switch()
            val = gdb.parse_and_eval(self.variable_name)

            # --- Non-intrusive read first ---
            if val.address:
                try:
                    val_type = val.type
                    val_size = val_type.sizeof
                    memory = gdb.selected_inferior().read_memory(val.address, val_size)
                    
                    if val_size == 8: self.data = struct.unpack('<Q', memory)[0]
                    elif val_size == 4: self.data = struct.unpack('<I', memory)[0]
                    elif val_size == 2: self.data = struct.unpack('<H', memory)[0]
                    elif val_size == 1: self.data = struct.unpack('<B', memory)[0]
                    else: self.data = f"Unsupported size: {val_size}"
                    return
                except gdb.MemoryError:
                    # Fall through to the intrusive method if memory is not valid
                    pass
            
            # --- Fallback to intrusive read (for registers) ---
            self.data = int(val)

        except gdb.error as e:
            self.data = f"Error: {e}"
            print(f"[gdb_debugger] tracer warning: could not read '{self.variable_name}': {e}")

    def stop(self):
        """This is a single-shot tracer, so stop is a no-op."""
        pass

    def __str__(self) -> str:
        return f"VariableTracer({self.variable_name})" 