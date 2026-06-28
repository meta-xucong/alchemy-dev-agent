# V2.121 Handler/Server Cleanup Timeout Split

## Problem

After V2.120, Billing Core phase_011 resumed correctly:

- T014 `Inventory legacy backend cleanup leftovers` completed.
- T015 `Clean service and repository legacy contracts` completed.
- T016 `Clean handler and server legacy routes` timed out after 900 seconds.

The timeout stop boundary worked again: no debug task or T017 dispatch was
launched. The remaining issue was that handler cleanup and server/command route
wiring were still combined in one worker.

The real graph probe also exposed a separate environment-indexing problem:
`.gomodcache` and `.gomodcache-local` directories were indexed as project
package roots, which polluted later verification commands with third-party
module test/build commands.

## Fix

Focused schema/build repairs that identify a handler/server cleanup timeout now
replace the broad route-cleanup task with:

- `Inventory handler and server cleanup leftovers`
- `Clean handler legacy route contracts`
- `Clean server route and command wiring`
- `Compile handler and server cleanup contracts`

The repository indexer now ignores `.gomodcache` and `.gomodcache-local`, in
addition to the existing generated/runtime cache directories, so Go module cache
contents cannot become package files, test commands, or build commands.

## Verification

- Focused planner regression for T016 handler/server cleanup timeout splitting.
- Focused repository-index regression for `.gomodcache` and `.gomodcache-local`
  exclusion.
- Real phase_011 graph probe with `phase_repair_001.md` through
  `phase_repair_010.md`: T014/T015 are preserved completed, T016 starts as
  read-only handler/server inventory, T017-T20 contain narrowed cleanup tasks,
  and T021/T022 contain only project backend/frontend verification commands.
