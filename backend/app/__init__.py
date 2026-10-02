"""
app/ — the only layer that knows about HTTP, streaming, persistence and logging.

`main.py`         FastAPI app: static mount + 6 routes
`models.py`       Pydantic request/response models (validation at the boundary)
`orchestrator.py` `run_audit` — the async generator that runs the whole pipeline
                  and yields one SSE line per stage
"""
