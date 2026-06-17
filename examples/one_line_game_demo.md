# One-Line Game Demo

## Purpose

This example records the current one-line generation capability.

It is intentionally narrow:

- It does not use external model calls.
- It does not clone a repository.
- It does not use real Codex worker sessions.
- It does not copy protected game assets, names, level layouts, or character designs.

It proves that the local contract path can produce a runnable artifact:

```text
Objective -> ProjectBrief -> ContextBundle -> TaskGraph -> Agent Events -> Artifact -> Review
```

## Command

```bash
python -m autodev.demo_run \
  --objective "我要生成一个超级玛丽第一关的游戏。关卡设计、人物和场景形象均完全模仿经典原始版的超级玛丽" \
  --output .alchemy/generated/retro_platformer_test
```

## Safety Handling

The original request asks for close imitation of a protected commercial game. The demo pipeline preserves the user's objective in `ProjectBrief`, but the `ContextBundle` converts delivery requirements into an original retro side-scrolling platformer.

Generated acceptance criteria:

- Playable original retro side-scrolling platformer.
- Canvas-rendered original pixel-style shapes.
- No external copyrighted assets.
- Movement, jumping, platform collision, coins, enemies, finish flag, timer, score, and restart.
- Local execution by opening `index.html`.

## Outputs

```text
.alchemy/generated/retro_platformer_test/
  index.html
  autodev_report.json
```

## Verified Result

The generated report returned:

```json
{
  "status": "done",
  "validation_errors": []
}
```

The local agent chain completed:

```text
architect -> frontend -> test -> reviewer
```

Browser verification confirmed:

- Page title: `Original Retro Platformer`
- Canvas: `960x540`
- HUD visible with score, coins, timer, and run state
- Control hint visible
- Rendered game scene visible with sky, platforms, coins, player, and gaps

## Current Boundary

This demo shows a working local generation loop, not the full target system.

Still missing for the full goal:

- Real multi-file document parsing.
- Private GitHub repository retrieval through optional `gh`.
- General repository-aware planning beyond local/public source indexing.
- General task graph generation for arbitrary apps.
- Real Agent SDK orchestration.
- Real Codex worker execution against a target repository.
- CI-driven completion gates.
- UI/API project intake.
