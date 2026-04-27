from open_router_key_viewer.core.query_execution_controller import (
    QueryExecutionController as _CoreQueryExecutionController,
)
from open_router_key_viewer.core.query_worker import QueryWorker
from open_router_key_viewer.core.threading import stop_thread


class QueryExecutionController(_CoreQueryExecutionController):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("worker_cls", QueryWorker)
        kwargs.setdefault("stop_thread_func", stop_thread)
        super().__init__(*args, **kwargs)

__all__ = ["QueryExecutionController"]
