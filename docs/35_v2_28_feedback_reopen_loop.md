# V2.28 Feedback Reopen Loop

V2.28 closes the post-delivery repair loop.

The original objective remains unchanged:

> A user provides detailed development documents, supporting files, feedback, and
> a GitHub repository; the agent system plans, implements, tests, fixes,
> verifies, and delivers until the result is review-ready.

Earlier versions made feedback files first-class intake. V2.28 adds the missing
operator path:

1. A delivered run exists.
2. The user uploads playtest notes, bug reports, or acceptance feedback.
3. The system reopens the project with the feedback files.
4. Feedback requirements are routed to Debug Agent tasks.
5. A new repair run starts with a feedback recovery branch prefix.
6. The new run produces normal delivery, coverage, browser, and GitHub evidence.

## Feedback Role Contract

Feedback files retain `role = feedback` through intake, context, and planning.

Requirements extracted from feedback include:

```json
{
  "source_role": "feedback",
  "priority": "must",
  "text": "Bug: clicking Add Todo does not update state.",
  "planned_task_ids": ["T002", "T005", "T006"]
}
```

The planner routes feedback requirements to:

```json
{
  "type": "debug",
  "assigned_agent": "debug"
}
```

This is intentionally different from normal feature implementation. Feedback is
repair work and should be handled by the Debug Agent.

## API Contract

The local API exposes:

```http
POST /projects/{project_id}/feedback/reopen
```

Request:

```json
{
  "source_run_id": "run_001",
  "feedback_files": ["D:/project/playtest_feedback.md"],
  "run": {
    "real_codex": true,
    "real_github": true,
    "auto_browser_verify": true
  }
}
```

Behavior:

- add feedback files to the project as required attachments
- rebuild intake and plan
- preserve the prior delivered run as `source_run_id`
- start a new run using `agent/feedback-recovery` as default worktree branch prefix
- record `feedback_reopen` evidence in the new run report

The endpoint does not require the prior run to contain failed tasks. Feedback
repair is a new iteration, not only a retry of a failed run.

## UI Contract

The browser console includes a `Feedback Reopen` control.

The operator flow is:

1. select feedback files
2. click `Feedback Reopen`
3. the console uploads the files with role `feedback`
4. the console calls `/feedback/reopen`
5. the delivery panel shows the new repair run

## Acceptance

V2.28 is complete when:

- feedback files keep `source_role = feedback` in the requirement map
- feedback requirements route to Debug Agent tasks
- the API can reopen a completed project with feedback files
- the new repair run records `feedback_reopen` metadata
- UI exposes a feedback reopen control
- unit tests, acceptance harness, JSON parsing, diff hygiene, state validation,
  and GitHub CI pass
