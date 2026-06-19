"""Local autonomous development demo pipeline."""

__all__ = [
    "AutoDevPipeline",
    "AutoDevResult",
    "DocumentRunPipeline",
    "DocumentRunResult",
    "ExecutionPreflight",
    "RealDeliveryValidation",
    "DeliveryValidationReport",
    "ExternalDocsOnlyAcceptance",
    "ExternalDocsOnlyAcceptanceReport",
    "build_development_cycle_report",
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
    if name in {"ExternalDocsOnlyAcceptance", "ExternalDocsOnlyAcceptanceReport"}:
        from .external_docs_only_acceptance import ExternalDocsOnlyAcceptance, ExternalDocsOnlyAcceptanceReport

        exports = {
            "ExternalDocsOnlyAcceptance": ExternalDocsOnlyAcceptance,
            "ExternalDocsOnlyAcceptanceReport": ExternalDocsOnlyAcceptanceReport,
        }
        return exports[name]
    if name == "build_development_cycle_report":
        from .development_cycle import build_development_cycle_report

        return build_development_cycle_report
    raise AttributeError(f"module 'autodev' has no attribute {name!r}")
