import gdb

class Tracer:
    """Base class for all tracers."""
    def __init__(self):
        self.data = None

    def start(self, inferior_thread: gdb.Thread):
        """
        Starts the tracer. This method should be implemented by subclasses
        to collect the desired data from the inferior.
        """
        raise NotImplementedError

    def stop(self):
        """
        Stops the tracer.
        """
        raise NotImplementedError

    def read_data(self):
        """
        Returns the collected data.
        """
        return self.data 