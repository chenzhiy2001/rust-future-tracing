class RuntimePlugin:
    """Minimal interface every async runtime plugin must implement."""

    name: str = "generic"

    def extra_breakpoints(self):
        """Return a list of additional symbol names where context-switches happen.
        e.g. for Tokio this could be task::schedule / poll.
        """
        return []

    def on_breakpoint(self, bp_name: str, inferior):
        """Called when any of the extra breakpoints fire.
        Return dict that will be stored in traceEvent.args.
        """
        return {} 