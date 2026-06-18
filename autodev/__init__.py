"""Local autonomous development demo pipeline."""

__all__ = ["AutoDevPipeline", "AutoDevResult", "DocumentRunPipeline", "DocumentRunResult"]


def __getattr__(name: str):
    if name in {"AutoDevPipeline", "AutoDevResult"}:
        from .pipeline import AutoDevPipeline, AutoDevResult

        exports = {
            "AutoDevPipeline": AutoDevPipeline,
            "AutoDevResult": AutoDevResult,
        }
        return exports[name]
    if name in {"DocumentRunPipeline", "DocumentRunResult"}:
        from .document_run import DocumentRunPipeline, DocumentRunResult

        exports = {
            "DocumentRunPipeline": DocumentRunPipeline,
            "DocumentRunResult": DocumentRunResult,
        }
        return exports[name]
    raise AttributeError(f"module 'autodev' has no attribute {name!r}")
