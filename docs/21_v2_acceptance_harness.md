# V2.12 Local Acceptance Harness

## Purpose

V2.12 adds a local acceptance harness that verifies the current document-driven product path without external credentials.

It is the last local gate before controlled real-repository validation.

## Command

```bash
python -m autodev.acceptance_run --output .alchemy/acceptance
```

The harness writes:

```text
.alchemy/acceptance/acceptance_report.json
```

## Coverage

The harness exercises:

- fixture repository creation
- development document intake
- supporting file intake
- ProjectBrief generation
- ContextBundle generation
- TaskGraph planning
- async run start
- event retrieval
- delivery summary retrieval
- final gate verification

## Report Checks

The report includes pass/fail checks for:

- project creation
- intake readiness
- task graph generation
- async job completion
- run completion
- event recording
- delivery completion
- final gate pass

## Boundary

The harness runs in deterministic dry-run mode. It validates the local contracts and product control path, but it does not prove arbitrary real repository completion with live Codex and GitHub PR/CI.

Real external validation remains a separate controlled phase.
