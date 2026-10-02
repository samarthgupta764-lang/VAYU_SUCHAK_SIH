"""
pipeline/ — PURE functions only.

Nothing in this package imports FastAPI, touches a database, opens a socket, or
writes a log line. Every function is `(data) -> (result, summary)` and can be
called from a shell with plain Python objects. The orchestrator (app/) is the
only place that knows about streaming, persistence and logging.
"""
