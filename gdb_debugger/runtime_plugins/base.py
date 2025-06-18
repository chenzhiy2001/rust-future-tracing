class RuntimePlugin:
    """
    Base class for runtime-specific plugins. A plugin defines what to trace
    and how to process the collected data.
    """
    @property
    def name(self):
        """Returns the name of the runtime (e.g., 'tokio')."""
        raise NotImplementedError

    def instrument_points(self):
        """
        Defines where to set breakpoints and which tracers to run.
        Should return a list of dictionaries, each with:
        {
            "symbol": str,
            "entry_tracers": [callable],  # List of functions that create Tracer objects
            "exit_tracers": [callable]
        }
        """
        raise NotImplementedError

    def process_data(self, all_traced_data: dict):
        """
        Processes and typically prints the data collected from all tracers.
        `all_traced_data` is a dictionary where keys are instrumented symbols
        and values are lists of trace results for each invocation.
        """
        raise NotImplementedError 