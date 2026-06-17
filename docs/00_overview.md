# Overview

## Problem

Modern AI coding agents can generate code, run tests, and iterate on failures, but complex software delivery needs more than a single long-running coding loop. A realistic development objective usually includes architecture decisions, task decomposition, repository constraints, implementation, testing, review, and delivery judgment.

The goal of this system is to define a specification for autonomous development that can move from a user objective to a delivery-ready result through structured planning, delegated execution, and measurable completion gates.

## Why This System Is Needed

A single agent loop is useful for local implementation work, but it becomes brittle when:

- The objective spans multiple subsystems.
- The correct order of work matters.
- Some tasks can run in parallel while others must wait.
- Different responsibilities require different standards.
- The system must know when to retry, escalate, or stop.
- Passing tests does not prove the result matches the user objective.

Autonomous software development needs a persistent state model and a task graph rather than a stream of loosely connected prompts.

## Limits Of Long-Running Codex Tasks

Codex long-running task workflows are strong at sustained coding and debugging, but they are not sufficient as the top-level control plane for an autonomous development system.

Key limitations:

- **Single-threaded control**: one execution context tends to serialize planning, coding, testing, and review.
- **Weak global state**: progress may be tracked in prose rather than a strict machine-readable state object.
- **No native dependency graph**: task ordering, blocking, and parallelism need an explicit graph model.
- **Ambiguous completion**: test pass can be mistaken for done even when acceptance criteria remain unmet.
- **Role blending**: architecture, implementation, review, and debugging can collapse into one perspective.
- **Limited supervision model**: repeated failure needs structured retry policy, blocker classification, and escalation.

Codex CLI is best treated as a capable execution worker, not as the central planner.

## Why Multi-Agent Execution

Multi-agent execution separates responsibilities so each agent can optimize for a specific kind of judgment.

Required separation:

- **Architect Agent** creates the development plan and task graph.
- **Backend Agent** owns server-side implementation tasks.
- **Frontend Agent** owns client-side implementation tasks.
- **Test Agent** owns verification design and test execution strategy.
- **Debug Agent** owns failure investigation and repair loops.
- **Reviewer Agent** validates final quality and specification alignment.

This separation reduces role conflict. The implementer should not be the only judge of whether implementation is complete.

## Why Graph Execution

A task graph makes the system operational.

It allows the orchestrator to:

- Identify ready tasks whose dependencies are complete.
- Run independent tasks in parallel.
- Assign specialized agents based on task type.
- Detect blocked or failed nodes.
- Retry only the affected subgraph.
- Preserve completion evidence per task.
- Evaluate final delivery against all required nodes.

The graph is the contract between planning, execution, and evaluation.

## Design Position

This repository defines a specification system for autonomous software development agents.

It is:

- Protocol-first.
- State-driven.
- Worker-agnostic except for the Codex CLI worker contract.
- Designed for GitHub repository execution.
- Focused on delivery-quality completion.

It is not:

- An app.
- A codebase for agents.
- A replacement for CI.
- A prompt collection.
- A single-agent coding loop.
