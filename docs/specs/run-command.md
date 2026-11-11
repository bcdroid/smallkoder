# Spec: `run_command` tool

- **Status:** implemented (commits `22cfc2c`..`f5c1ac9`, 2026-11-09; missing-bash fix 2026-11-11)
- **Written:** 2026-11-11, *after* the implementation, from the code and tests. Future
  features get their spec before the code (see [CLAUDE.md](../../CLAUDE.md)).
- **Backlog item:** "Bash / run-command tool with a permission prompt"
- **Decisions:** [ADR 0002](../adr/0002-approve-every-command.md),
  [0003](../adr/0003-approval-is-the-only-command-guardrail.md),
  [0004](../adr/0004-separate-command-approval-callback.md),
  [0005](../adr/0005-kill-the-whole-process-group.md),
  [0006](../adr/0006-recorded-commands-run-for-real-on-replay.md)

## Goal

Let the model run shell commands (programs, tests, git, linters) in the user's project,
with the user approving each one. Until now the model could only read and write files.

## Non-goals

- Running commands without asking: no allow-list, no "always" answer
  (backlog: "Fewer command prompts").
- Containing what an approved command can do: no sandbox, no checks on the command
  text (backlog: "Sandboxing commands").
- Windows support (backlog: "`run_command` is POSIX only").
- Showing the command's output to the user (backlog: "Show command output to the user").
- Interactive commands, long-running servers, or streaming output.

## Interface

### Tool schema (sent to the model)

The last entry in `TOOLS` (`smallkoder/tools.py`), after the file tools `read_file`, `write_file`
and `edit_file` (added 2026-11-11, see [edit-file.md](edit-file.md)):

| Field | Value |
|---|---|
| name | `run_command` |
| parameters | `command` (string, required); no others (`additionalProperties: false`) |
| description | Says: bash, working directory, exit code and output, stdout and stderr together, the last `OUTPUT_LIMIT` characters, `COMMAND_TIMEOUT` seconds, cannot read input, the user approves each command |

The system prompt names all the tools and asks the model to use `run_command` for
programs, tests and git, not for reading or writing files, and not to retry a declined
command unless asked. It contains no `/`, so traces stay portable.

### Python API

```python
run_command(root: Path, command: str, approve_command, timeout: float = COMMAND_TIMEOUT) -> str
run_tool(name, arguments, root, approve, approve_command=never) -> str
run_turn(model, messages, user_text, root, approve, max_steps=20, on_tool=None, approve_command=never) -> str
```

`approve_command(command: str) -> bool` asks the user. `never` always returns `False`,
so a caller that passes no approver gets every command declined.

Constants: `COMMAND_TIMEOUT = 30` (seconds), `OUTPUT_LIMIT = 10_000` (characters).

## Behaviour

In order:

1. **Empty command.** If `command.strip()` is empty, fail with `command is empty`
   *without* asking the user.
2. **Approval.** Call `approve_command(command)`. If it returns false, fail with
   `the user declined this command`. Nothing runs.
3. **Run** `["bash", "-c", command]` with:
   - working directory: `root`;
   - environment: smallkoder's own environment minus `OPENCODE_GO`;
   - stdin: `/dev/null`, so a command that reads input gets EOF at once;
   - stdout: a pipe; stderr: merged into stdout, in the order written;
   - a new session (`start_new_session=True`), so the command and everything it starts
     share one process group, separate from smallkoder's.

   If the process can't be started (`OSError`: no `bash` on the `PATH`, a working
   directory that has gone), fail with `could not start bash: <the OS error>`. `bash` is
   looked up on the `PATH` of the command's environment.
4. **Wait** up to `timeout` seconds for the output pipe to close and the process to exit.
5. **Result.** Return `Exit code: <N>\n<output>`. `<output>` is decoded as UTF-8 with
   invalid bytes replaced, then cut by `keep_end`. A non-zero exit code is a normal
   result, not an error.

`keep_end(text, limit)` returns `text` unchanged if it fits. Otherwise it returns
`[... <cut> characters cut ...]\n` followed by the last `limit` characters (the end is
where errors and test summaries usually are).

### Timeout

On timeout, send `SIGKILL` to the whole process group, reap the process, collect the
output printed so far, and fail with:

```
command timed out after <timeout> s. Output so far:
<keep_end(output)>
```

A command that leaves a background child holding the pipe (`sleep 30 & echo started`)
times out too, because the pipe stays open. Killing the group stops the child, so
smallkoder never waits longer than the timeout.

### Ctrl-C

The command is in its own session, so the terminal's Ctrl-C goes to smallkoder only.
On any exception while waiting (in practice `KeyboardInterrupt`), kill the group, reap
it, and re-raise. The CLI then quits as before.

### Errors

As with every tool, failures are `ToolError`s, which `run_tool` turns into
`Error: ...` results for the model:

| Situation | Tool result |
|---|---|
| Empty or whitespace command | `Error: command is empty` |
| User said no, or no approver given | `Error: the user declined this command` |
| Timeout | `Error: command timed out after 30 s. Output so far:\n...` |
| `bash` can't be started | `Error: could not start bash: [Errno 2] No such file or directory: 'bash'` |
| Missing or extra argument, not a string | the usual `parse_arguments` errors |

## The CLI

`repl()` passes an `approve_command` that prints

```
  The model wants to run: <command, in full>
  Run this command? [y/N]
```

Only `y` or `yes` (any case, surrounding spaces ignored) approves. Anything else,
including EOF, declines. The command is never shortened: the user must see exactly
what they approve. The `[run_command] {...}` line from `on_tool` is still shortened like
every other tool call.

## Guardrails: what does and does not apply

| Guardrail | File tools | `run_command` |
|---|---|---|
| Paths confined to the working directory | yes | **no** |
| `.env` refused | yes | **no** (`cat .env` works if approved) |
| User approval | writes only | every command |
| `OPENCODE_GO` hidden | n/a | yes, from the environment |
| Step limit, errors as results | yes | yes |

Why there is no command-text check: [ADR 0003](../adr/0003-approval-is-the-only-command-guardrail.md).

## Traces

- `record_session` and the replay helper pass one approver as both `approve` and
  `approve_command`. A trace's `approvals` list holds write and command answers
  together, in the order they were asked.
- On replay, commands run again for real ([ADR 0006](../adr/0006-recorded-commands-run-for-real-on-replay.md)),
  so recorded scenarios use commands whose output is the same on every machine.
- Scenarios: `run_program` (`python3 hello.py`, approved) and `declined_command`
  (`rm notes.txt`, declined; the file must survive).

## Tests

| Behaviour | Test |
|---|---|
| Exit code and output, working directory, stderr merged, bash syntax | `tests/test_tools.py::test_run_command_*` |
| Declined: nothing runs; empty: not asked | `test_run_command_declined_does_not_run`, `..._refuses_empty_command_without_asking` |
| Key hidden, stdin closed | `test_run_command_hides_the_api_key`, `..._cannot_read_input` |
| No `bash`: an error result, not a crash | `test_run_command_without_bash_is_a_tool_error`, `test_run_tool_without_bash_reports_an_error` |
| Timeout with partial output; background child killed | `..._times_out_and_keeps_partial_output`, `..._timeout_kills_background_children` |
| Ctrl-C kills the process group | `test_run_command_ctrl_c_kills_the_command` |
| Output limit | `test_keep_end_*`, `test_run_command_output_is_limited` |
| Default approver declines | `test_run_tool_refuses_commands_when_no_approver_is_given`, `tests/test_agent.py::test_commands_are_declined_by_default` |
| CLI prompt, full command shown, anything but yes declines, EOF declines | `tests/test_cli.py::test_command_*`, `..._a_command`, `..._command_prompt_declines` |
| Shared approvals in traces | `tests/test_traces.py::test_record_session_shares_approvals_between_writes_and_commands` |
| Real model sessions | `tests/test_recorded_sessions.py::test_run_program_returns_its_output`, `..._declined_command_does_not_run` |

## Known gaps

- ~~**`bash` not installed.**~~ Fixed 2026-11-11. Writing this spec found it: `Popen`
  raised `FileNotFoundError`, which escaped `run_tool` and ended the session. It is now
  an error result (see Errors).
- POSIX only (`bash`, `start_new_session`, `os.killpg`).
- A process that calls `setsid` itself leaves the group and survives a kill.
- Output is read whole into memory before being cut; a command printing gigabytes
  would use that much memory until the timeout.
