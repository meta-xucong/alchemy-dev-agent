"""Local autonomous development demo pipeline."""

__all__ = [
    "AutoDevPipeline",
    "AutoDevResult",
    "DocumentRunPipeline",
    "DocumentRunResult",
    "ExecutionPreflight",
    "RealDeliveryValidation",
    "DeliveryValidationReport",
    "RealUnifiedDeliveryHarness",
    "RealUnifiedDeliveryReport",
    "GitHubPRLifecycle",
    "PullRequestLifecycleReport",
    "EvidencePackageExporter",
    "EvidencePackageReport",
    "BenchmarkSuite",
    "BenchmarkSuiteReport",
    "BenchmarkRegressionGate",
    "BenchmarkRegressionReport",
    "EvidenceReadinessGate",
    "EvidenceReadinessReport",
    "ExternalDocsOnlyAcceptance",
    "ExternalDocsOnlyAcceptanceReport",
    "LocalRepositoryAcceptanceHarness",
    "LocalRepositoryAcceptanceResult",
    "build_development_cycle_report",
    "FullRoadmapExecutor",
    "FullRoadmapExecutionResult",
    "ProjectAnalysisGate",
    "ProjectAnalysisReport",
    "RoadmapExtractor",
    "RoadmapAuditor",
    "FinalVerificationLoop",
    "FinalVerificationReport",
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
    if name in {"RealUnifiedDeliveryHarness", "RealUnifiedDeliveryReport"}:
        from .real_unified_delivery import RealUnifiedDeliveryHarness, RealUnifiedDeliveryReport

        exports = {
            "RealUnifiedDeliveryHarness": RealUnifiedDeliveryHarness,
            "RealUnifiedDeliveryReport": RealUnifiedDeliveryReport,
        }
        return exports[name]
    if name in {"GitHubPRLifecycle", "PullRequestLifecycleReport"}:
        from .github_pr_lifecycle import GitHubPRLifecycle, PullRequestLifecycleReport

        exports = {
            "GitHubPRLifecycle": GitHubPRLifecycle,
            "PullRequestLifecycleReport": PullRequestLifecycleReport,
        }
        return exports[name]
    if name in {"EvidencePackageExporter", "EvidencePackageReport"}:
        from .evidence_package import EvidencePackageExporter, EvidencePackageReport

        exports = {
            "EvidencePackageExporter": EvidencePackageExporter,
            "EvidencePackageReport": EvidencePackageReport,
        }
        return exports[name]
    if name in {"BenchmarkSuite", "BenchmarkSuiteReport"}:
        from .benchmark_suite import BenchmarkSuite, BenchmarkSuiteReport

        exports = {
            "BenchmarkSuite": BenchmarkSuite,
            "BenchmarkSuiteReport": BenchmarkSuiteReport,
        }
        return exports[name]
    if name in {"BenchmarkRegressionGate", "BenchmarkRegressionReport"}:
        from .benchmark_regression import BenchmarkRegressionGate, BenchmarkRegressionReport

        exports = {
            "BenchmarkRegressionGate": BenchmarkRegressionGate,
            "BenchmarkRegressionReport": BenchmarkRegressionReport,
        }
        return exports[name]
    if name in {"EvidenceReadinessGate", "EvidenceReadinessReport"}:
        from .evidence_readiness import EvidenceReadinessGate, EvidenceReadinessReport

        exports = {
            "EvidenceReadinessGate": EvidenceReadinessGate,
            "EvidenceReadinessReport": EvidenceReadinessReport,
        }
        return exports[name]
    if name in {"ExternalDocsOnlyAcceptance", "ExternalDocsOnlyAcceptanceReport"}:
        from .external_docs_only_acceptance import ExternalDocsOnlyAcceptance, ExternalDocsOnlyAcceptanceReport

        exports = {
            "ExternalDocsOnlyAcceptance": ExternalDocsOnlyAcceptance,
            "ExternalDocsOnlyAcceptanceReport": ExternalDocsOnlyAcceptanceReport,
        }
        return exports[name]
    if name in {"LocalRepositoryAcceptanceHarness", "LocalRepositoryAcceptanceResult"}:
        from .local_repository_acceptance import LocalRepositoryAcceptanceHarness, LocalRepositoryAcceptanceResult

        exports = {
            "LocalRepositoryAcceptanceHarness": LocalRepositoryAcceptanceHarness,
            "LocalRepositoryAcceptanceResult": LocalRepositoryAcceptanceResult,
        }
        return exports[name]
    if name == "build_development_cycle_report":
        from .development_cycle import build_development_cycle_report

        return build_development_cycle_report
    if name in {"FullRoadmapExecutor", "FullRoadmapExecutionResult"}:
        from .full_roadmap_executor import FullRoadmapExecutionResult, FullRoadmapExecutor

        exports = {
            "FullRoadmapExecutor": FullRoadmapExecutor,
            "FullRoadmapExecutionResult": FullRoadmapExecutionResult,
        }
        return exports[name]
    if name in {"ProjectAnalysisGate", "ProjectAnalysisReport"}:
        from .project_analysis_gate import ProjectAnalysisGate, ProjectAnalysisReport

        exports = {
            "ProjectAnalysisGate": ProjectAnalysisGate,
            "ProjectAnalysisReport": ProjectAnalysisReport,
        }
        return exports[name]
    if name == "RoadmapExtractor":
        from .roadmap_extractor import RoadmapExtractor

        return RoadmapExtractor
    if name == "RoadmapAuditor":
        from .roadmap_auditor import RoadmapAuditor

        return RoadmapAuditor
    if name in {"FinalVerificationLoop", "FinalVerificationReport"}:
        from .final_verification_loop import FinalVerificationLoop, FinalVerificationReport

        exports = {
            "FinalVerificationLoop": FinalVerificationLoop,
            "FinalVerificationReport": FinalVerificationReport,
        }
        return exports[name]
    raise AttributeError(f"module 'autodev' has no attribute {name!r}")
