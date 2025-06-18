from gdb_debugger.tracers.base import Tracer
import gdb

class BacktraceTracer(Tracer):
    """A tracer that captures the call stack of a thread."""
    def __init__(self):
        super().__init__()

    def start(self, inferior_thread: gdb.Thread):
        """
        Captures the backtrace when started.
        """
        frames = []
        try:
            inferior_thread.switch()
            frame = gdb.selected_frame()
            while frame:
                frame_info = {
                    "pc": frame.pc(),
                    "name": None,
                }
                sal = frame.find_sal()
                if sal and sal.symtab:
                    frame_info["name"] = frame.name()
                frames.append(frame_info)
                frame = frame.older()
            self.data = frames
        except gdb.error as e:
            self.data = f"Error: {e}"
            print(f"[gdb_debugger] tracer warning: could not get backtrace: {e}")

    def stop(self):
        """This is a single-shot tracer, so stop is a no-op."""
        pass
        
    def __str__(self) -> str:
        return "BacktraceTracer" 