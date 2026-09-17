import logging

# where uvicorn's access log call puts the path in its record arguments:
# (client address, method, path with query string, HTTP version, status)
_ACCESS_LOG_PATH_ARG = 2


class DropQueryString(logging.Filter):
    """Log request paths without their query string.

    Query strings carry what users typed: searching the order list for a
    buyer's email sends it as `?search=...`, and the access log wrote it out
    with every request. The path alone is enough to see what was called.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) > _ACCESS_LOG_PATH_ARG:
            path = args[_ACCESS_LOG_PATH_ARG]
            if isinstance(path, str) and "?" in path:
                record.args = (
                    *args[:_ACCESS_LOG_PATH_ARG],
                    # ASCII: a Windows console shows "…" as mojibake
                    path.split("?", 1)[0] + "?...",
                    *args[_ACCESS_LOG_PATH_ARG + 1 :],
                )
        return True


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    access_log = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, DropQueryString) for f in access_log.filters):
        access_log.addFilter(DropQueryString())
