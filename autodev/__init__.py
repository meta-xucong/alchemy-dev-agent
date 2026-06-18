"""Local autonomous development demo pipeline."""

__all__ = [
    "AutoDevPipeline",
    "AutoDevResult",
    "DocumentRunPipeline",
    "DocumentRunResult",
    "ExecutionPreflight",
    "RealDeliveryValidation",
    "DeliveryValidationReport",
]


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
    if name == "ExecutionPreflight":
        from .preflight import ExecutionPreflight

        return ExecutionPreflight
    if name in {"RealDeliveryValidation", "DeliveryValidationReport"}:
        from .real_delivery_validation import DeliveryValidationReport, RealDeliveryValidation

        exports = {
            "DeliveryValidationReport": DeliveryValidationReport,
            "RealDeliveryValidation": RealDeliveryValidation,
        }
        return exports[name]
    raise AttributeError(f"module 'autodev' has no attribute {name!r}")
