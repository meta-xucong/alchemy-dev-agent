# V2.27 Acceptance Scenario Browser Probes

V2.27 extends the document-driven delivery loop with deterministic browser
scenarios generated from detailed acceptance requirements.

The objective is unchanged:

> Detailed development documents and supporting files should drive automated
> planning, implementation, testing, feedback repair, and GitHub delivery.

V2.26 introduced a generic semantic web probe. That probe answers:

- does the page render
- are controls discoverable
- can safe controls be exercised
- does a visible state change occur

V2.27 adds a more specific layer for common product flows:

- CRUD
- authentication
- file upload
- dashboard, metrics, filters, and tables

## Contract

The system now builds an `acceptance_scenarios` plan from the structured
requirement map.

Each scenario contains:

```json
{
  "id": "SCN-001",
  "kind": "crud",
  "title": "CRUD acceptance scenario",
  "source_requirement_id": "REQ-002",
  "required_behaviors": ["create", "update", "delete", "list"],
  "evidence_terms": ["crud", "todo/task/item/record"]
}
```

Scenario generation is deterministic. It does not call a model and does not
invent product scope. It only recognizes explicit requirement and acceptance
criteria terms.

## Browser Probe

When automatic browser verification runs for `static_web_app` artifacts, the
browser runner receives the generated scenarios and writes:

```json
{
  "scenario_probe": {
    "status": "completed",
    "summary": "Acceptance scenario probe passed.",
    "tests_passed": [
      "SCN-001: CRUD create controls are present."
    ],
    "tests_failed": [],
    "scenarios": []
  }
}
```

Failure of a generated scenario becomes delivery evidence and affects the
development-cycle testing step. This prevents a page from passing generic
render checks while missing document-specific flows such as login, upload, or
dashboard controls.

## Scenario Rules

### CRUD

Detected from terms such as:

- CRUD
- create, add, edit, update, delete, remove
- todo, task, item, record
- 新增, 添加, 创建, 编辑, 修改, 更新, 删除, 待办, 任务

Checks include:

- create/input controls
- read/list surface
- update controls when requested
- delete controls when requested

### Authentication

Detected from terms such as:

- login, sign in, register, password, session
- 登录, 注册, 密码, 会话

Checks include:

- credential input
- password/session field for login flows
- submit/login/register control

### File Upload

Detected from terms such as:

- upload, import, attachment, file picker, dropzone
- 上传, 导入, 附件, 文件选择

Checks include:

- file input or visible upload/import control

### Dashboard

Detected from terms such as:

- dashboard, analytics, metric, KPI, chart, table, report, filter, search
- 仪表盘, 看板, 统计, 指标, 图表, 报表, 表格, 筛选, 搜索

Checks include:

- metric/report surface
- filter/search controls when requested

## Worker Guidance

Codex worker prompts now explicitly ask generated static web apps to expose
semantic labels and visible controls for CRUD, authentication, upload, and
dashboard flows when those flows are mentioned by acceptance criteria.

## Reporting

Scenario evidence is surfaced in:

- `artifact_report.acceptance_scenarios`
- `artifact_report.browser_verification.scenario_probe`
- `delivery_report.artifact.scenario_status`
- `delivery_report.artifact.scenario_probe`
- `requirement_coverage.verification_evidence`
- `development_cycle.testing`
- browser console delivery summary

## Acceptance

V2.27 is complete when:

- acceptance scenarios are generated from requirement and acceptance text
- browser verification receives and evaluates those scenarios
- scenario failures block testing readiness
- scenario evidence appears in delivery and coverage reports
- unit tests, real Playwright scenario smoke, acceptance harness, JSON parsing,
  diff hygiene, long-running state validation, and GitHub CI pass
