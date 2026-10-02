"""
A single stop mechanism for pipelines and handlers.

StopSignal wraps the stop flag as one shared, thread-safe object. It can
be passed through the UI layer (Gradio gr.State), the pipeline layer and
the handler layer, so that a running job can be stopped from wherever the
request comes in.

Usage:

    stop = StopSignal()
    pipeline.run(material, ..., stop=stop)
    # or in a handler:
    if stop.is_stopped:
        return early
    stop.request()  # triggered by the UI
"""


class StopSignal:
    """Stop flag with three methods: request, reset, is_stopped.

    Thread-safe for read and write access at the granularity Python bools
    guarantee (atomic). Sufficient for asynchronous workflows, because
    coroutines do not access memory in parallel.
    """

    __slots__ = ("_stop",)

    def __init__(self) -> None:
        self._stop: bool = False

    def request(self) -> None:
        """Sets the stop flag — all consumers stop at their next check."""
        self._stop = True

    def reset(self) -> None:
        """Resets the flag — typically called before a new pipeline run."""
        self._stop = False

    @property
    def is_stopped(self) -> bool:
        return self._stop

    def __bool__(self) -> bool:
        """Erlaubt `if stop: break` als Kurzform."""
        return self._stop

    def __repr__(self) -> str:
        return f"StopSignal({'stopped' if self._stop else 'running'})"
