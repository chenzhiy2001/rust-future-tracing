from .base import RuntimePlugin

class TokioPlugin(RuntimePlugin):
    name = "tokio"

    def extra_breakpoints(self):
        # names taken from Tokio 1.x default scheduler internals
        return [
            "tokio::runtime::task::raw::poll",
            "tokio::runtime::task::raw::schedule",
        ]

    def on_breakpoint(self, bp_name: str, inferior):
        return {"tokio_evt": bp_name} 