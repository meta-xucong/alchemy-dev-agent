"""V2.22 docs-only repository acceptance harness."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .document_run import DocumentRunPipeline


@dataclass(slots=True)
class ExternalDocsOnlyAcceptanceReport:
    status: str
    checks: list[dict[str, object]] = field(default_factory=list)
    document_run: dict[str, object] = field(default_factory=dict)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": list(self.checks),
            "document_run": dict(self.document_run),
            "output_dir": self.output_dir,
        }


class ExternalDocsOnlyAcceptance:
    """Exercise the external docs-only planning contract with a local fixture."""

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/external_docs_only_acceptance",
        keep: bool = False,
    ) -> ExternalDocsOnlyAcceptanceReport:
        output = Path(output_dir)
        if output.exists() and not keep:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        repo = output / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        spec = output / "super_mario_level1_spec.md"
        write_platformer_spec(spec)

        result = DocumentRunPipeline().run(
            objective=(
                "Build an original retro platformer first level from the provided development document; "
                "preserve engineering requirements but do not copy protected Nintendo characters, art, names, or exact level layouts."
            ),
            documents=[spec],
            repository_url="https://github.com/meta-xucong/-super-mario-test",
            repository_path=repo,
            output_dir=output / "document_run",
        )
        payload = result.to_dict()
        requirements = payload["context_bundle"]["requirement_map"]["requirements"]
        graph = payload["task_graph"]
        verify_nodes = [
            node for node in graph["nodes"] if node["title"] == "Verify implementation against project checks"
        ]
        checks = [
            check("document_driven", payload["project_brief"]["primary_input_mode"] == "document_driven", payload["project_brief"]["primary_input_mode"]),
            check("no_one_line_fallback", all(req["source_document_id"] != "generated_one_line" for req in requirements), [req["source_document_id"] for req in requirements]),
            check("requirement_count", len(requirements) >= 10, len(requirements)),
            check("document_plan_graph", str(graph["graph_id"]).endswith("-document-plan"), graph["graph_id"]),
            check("artifact_gate_planned", bool(verify_nodes and verify_nodes[0]["commands_to_run"] == ["static artifact inspection"]), verify_nodes[0]["commands_to_run"] if verify_nodes else []),
            check("scaffold_files_planned", scaffold_files_present(graph), planned_files(graph)),
        ]
        status = "passed" if all(item["passed"] for item in checks) else "failed"
        report = ExternalDocsOnlyAcceptanceReport(
            status=status,
            checks=checks,
            document_run=payload,
            output_dir=str(output),
        )
        (output / "external_docs_only_acceptance_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report


def planned_files(graph: dict[str, object]) -> list[str]:
    files: list[str] = []
    for node in graph.get("nodes", []):
        if isinstance(node, dict):
            files.extend(str(file) for file in node.get("relevant_files", []))
    return sorted(set(files))


def scaffold_files_present(graph: dict[str, object]) -> bool:
    files = set(planned_files(graph))
    required = {
        "index.html",
        "src/main.js",
        "src/engine.js",
        "src/input.js",
        "src/physics.js",
        "src/tilemap.js",
        "src/entities.js",
        "src/renderer.js",
        "tests/static_checks.js",
    }
    return required.issubset(files)


def check(name: str, passed: bool, detail: object) -> dict[str, object]:
    return {"name": name, "passed": passed, "detail": detail}


def write_platformer_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "## 目的",
                "本 PR 添加《超级玛丽类横版游戏》第一关完整工程化开发文档。",
                "",
                "## 内容说明",
                "- 游戏核心系统拆分（Engine / Physics / Renderer / Input / Entity）",
                "- TileMap 关卡定义规范",
                "- 玩家 / 敌人 / 金币 / 旗帜行为定义",
                "- 碰撞系统设计（AABB + Tile Collision）",
                "- 游戏状态机设计",
                "- 分数系统与通关条件",
                "- 性能与架构要求",
                "- 文件结构规范",
                "- 开发里程碑拆解",
                "",
                "## 技术目标",
                "- 可完整通关的第一关",
                "- 60 FPS Canvas 渲染",
                "- 基于 TileMap 的关卡系统",
                "- 基础敌人 AI（Goomba）",
                "- 玩家跳跃与物理系统",
                "- 胜利判定（旗帜触发）",
                "",
                "## 下一步计划",
                "1. Game Engine 初始化",
                "2. Player 移动与物理",
                "3. TileMap 渲染系统",
                "4. 碰撞系统",
                "5. Enemy AI",
                "6. Level 1 完整跑通",
            ]
        ),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run V2.22 external docs-only acceptance checks.")
    parser.add_argument("--output", default=".alchemy/external_docs_only_acceptance")
    parser.add_argument("--keep", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = ExternalDocsOnlyAcceptance().run(output_dir=args.output, keep=args.keep)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
