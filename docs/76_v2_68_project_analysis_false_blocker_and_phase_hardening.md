# V2.68 Project Analysis False-Blocker And Phase Hardening

## Objective

V2.68 hardens the pre-development analysis gate so a full-roadmap run can safely start from a large document package without human interpretation.

The goal remains the original Alchemy Dev Agent goal:

```text
user supplies objective/docs/repository
-> central brain reads the full package
-> extracts the real development roadmap
-> rejects only real human/infrastructure blockers
-> lets Codex workers execute every required phase until final handoff
```

## Triggering Real-Run Finding

A real `alchemy-media-agent` V3 full-roadmap probe stopped before code execution because the analysis layer misclassified normal document text as hard blockers:

```text
The user should not need to manually select models, prompts, seeds, samplers, LoRAs, ControlNet maps, or workflow nodes.
requires_gpu: bool
```

The first line is a product automation requirement. The second line is a schema field declaration. Neither requires human help before development starts.

A follow-up dry-run also showed that code-fenced roadmap summaries and reference-map recommendations could be promoted into primary development phases. That caused extra phases such as:

```text
Phase 1: Study and absorb ideas only
Phase 4: Add heavy model sidecars
```

Those lines are useful reference material, but they are not the canonical full-roadmap execution sequence when versioned V3 phases already exist.

## Required Behavior

### External Blocker Classification

The roadmap extractor must treat a line as an external blocker only when it represents a real missing capability or resource that the system cannot satisfy automatically.

Examples that may block:

```text
Real provider execution requires API key configuration.
Private repository access requires GitHub CLI authentication.
Production GPU deployment requires a configured GPU runner.
```

Examples that must not block:

```text
The user should not need to manually select models or workflow nodes.
No heavy GPU dependency is required for foundation tests.
requires_gpu: bool
provider_name: string
Do not add ControlNet in this phase.
```

### Phase Extraction

The extractor must prefer real development headings over summary lists:

```text
## 2. V3.0 Foundation
## 3. V3.1 Brand Consistency Foundation
```

Code-fenced wave lists may be used as fallback only when no better heading exists for that version.

Reference documents may contribute constraints, context, and ideas, but when a versioned roadmap already exists, generic `Phase N` headings from reference maps must not become root execution phases.

## Acceptance Criteria

- Product automation requirements do not become external blockers.
- Schema field declarations do not become external blockers.
- Real resource requirements still become external blockers.
- Numbered Markdown headings such as `## 2. V3.0 Foundation` are recognized as real phases.
- Code-fenced phase summaries do not override richer Markdown sections.
- Reference-map `Phase N` recommendations do not pollute a V3 versioned roadmap.
- An `alchemy-media-agent` V3 document dry-run starts with no external blockers and executes the real V3 phase sequence.

## Verification Evidence

The V2.68 fix is considered valid when these checks pass:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_full_roadmap_execution -v
python -B -m compileall autodev context planner runtime server tests
python -B -m autodev.run --full-roadmap --execution-mode dry_run ...
```

Expected dry-run result for the `alchemy-media-agent` V3 package:

```text
status=done
project_analysis.start_decision=start
external_blockers=[]
valid_phase_count=8
phase_record_count=8
final_audit.status=passed
```

## Non-Goals

- Do not implement target-project media features inside Alchemy Dev Agent.
- Do not loosen V1/V2 protection boundaries.
- Do not allow phase completion to stop the parent roadmap run.
- Do not treat optional real provider integration as required unless the source roadmap explicitly makes it a required phase.
