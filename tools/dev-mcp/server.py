"""Anvero's handy dev-loop MCP server.

Wraps the PowerShell scripts under `scripts/` as MCP tools, so an assistant
(or a human, through an MCP-aware client) can run them by name instead of
memorising PowerShell syntax. The scripts themselves stay the source of
truth - this file has no logic of its own beyond "run the script and hand
back its output"; fix a tool's behaviour in the .ps1, not here.

Run directly for a manual smoke test (talks stdio, so it just waits):
    .venv\\Scripts\\python.exe server.py
Normally launched by an MCP client per the repo's `.mcp.json`.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# tools/dev-mcp/server.py -> tools/dev-mcp -> tools -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

mcp = FastMCP("anvero-dev-tools")


def _run_powershell_script(script_name: str, args: list[str] | None = None, timeout: int = 60) -> str:
    script = SCRIPTS_DIR / script_name
    if not script.exists():
        return f"error: {script} does not exist"

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *(args or []),
    ]

    # `restart-backend.ps1` starts a long-lived server via Start-Process, and
    # on Windows that grandchild inherits PowerShell's own stdio handles
    # (.NET's CreateProcess call enables handle inheritance whenever any
    # redirection is used, not just the one it means to redirect). With
    # capture_output=True those handles are anonymous pipes, so this call
    # would wait forever for an EOF that only comes once every holder of the
    # pipe closes it - including the server we just told to keep running.
    # Real files sidestep that: subprocess.run then just waits for
    # powershell.exe itself to exit, not for a pipe a grandchild still holds.
    #
    # The same inheritance means the started server can still hold one of
    # these two files open afterwards, so deleting them can fail with
    # WinError 32 ("used by another process"); left for the OS's normal temp
    # cleanup instead, the same way the script's own server log already is.
    fd_out, out_path = tempfile.mkstemp(suffix=".log", prefix="anvero-mcp-out-")
    fd_err, err_path = tempfile.mkstemp(suffix=".log", prefix="anvero-mcp-err-")
    os.close(fd_out)
    os.close(fd_err)
    try:
        with open(out_path, "w") as out_file, open(err_path, "w") as err_file:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=out_file,
                stderr=err_file,
                text=True,
                timeout=timeout,
            )
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        exit_code = None

    stdout = Path(out_path).read_text(errors="replace")
    stderr = Path(err_path).read_text(errors="replace")
    for path in (out_path, err_path):
        try:
            os.remove(path)
        except OSError:
            pass  # still held open by a process this tool started on purpose

    output = stdout
    if stderr:
        output += "\n--- stderr ---\n" + stderr
    if exit_code is None:
        output += f"\n--- timed out after {timeout}s; a started server may still be running in the background ---"
    else:
        output += f"\n--- exit code: {exit_code} ---"
    return output


@mcp.tool()
def restart_backend(port: int = 8000, reload: bool = False) -> str:
    """Cleanly restart Anvero's FastAPI backend on Windows.

    Stops whatever currently holds the port - including an orphaned
    `uvicorn --reload` worker, the exact trap CLAUDE.md warns about, where
    killing only the parent leaves a process still answering with stale
    code - starts a fresh server, and waits for `GET /api/v1/health` to
    answer before returning, so "it's running" is checked rather than
    assumed. Runs `scripts/restart-backend.ps1`.

    Set `reload=True` only for a short edit-and-reload session; every
    reload-triggered restart risks leaving the same kind of orphan this
    tool exists to clean up after, so the default is off.
    """
    args = ["-Port", str(port)]
    if reload:
        args.append("-Reload")
    return _run_powershell_script("restart-backend.ps1", args, timeout=40)


@mcp.tool()
def sync_test_counts() -> str:
    """Run both test suites and update the test-count numbers in the docs.

    Runs the backend pytest suite and the frontend vitest suite, reads the
    passing counts back out of their own output, and replaces just the
    numbers - "NNN backend" / "NNN frontend" - in `docs/PROJECT_STATUS.md`,
    `docs/AI_START_HERE.md` and `docs/AI_HANDOFF.md`, leaving the rest of
    each sentence as its author wrote it. Nothing is committed; review the
    diff afterwards. Runs `scripts/sync-test-counts.ps1`. Takes under a
    minute.
    """
    return _run_powershell_script("sync-test-counts.ps1", timeout=180)


if __name__ == "__main__":
    mcp.run()
