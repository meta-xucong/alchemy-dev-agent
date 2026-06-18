# V2.19 Representative Delivery Probe

## Purpose

The V2.19 representative delivery probe validates document-driven delivery with
a small, bounded documentation task. It proves that requirements, allowed file
boundaries, worker evidence, and verification results can move through the real
execution path together.

## Execution Boundary

Real worker execution happens inside an isolated git worktree.

The source checkout safety requirement is that the source checkout remains
unchanged during worker execution. Task-local edits, generated evidence, and
tests belong in the worker worktree.

## Scope

This probe creates documentation only. It does not introduce new runtime
features, change worker behavior, or alter delivery orchestration.

## Verification

Generated evidence should include:

- static document inspection for the required V2.19 representative delivery
  probe language
- confirmation that tests or checks requested by the task package were run, or
  an explicit note when no runtime tests apply
