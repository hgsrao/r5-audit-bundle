"""Local MCP delegation bridge to the installed Claude Code CLI.

No listener, API key handling, shell interpolation, or permission bypass.
Jobs and receipts survive an MCP client reconnect.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid

BASE = Path(__file__).resolve().parent
CLAUDE = Path('/home/srinivas/.config/Claude/claude-code/2.1.284/claude')
JOBS = BASE / 'jobs'
ROOTS = [Path('/home/srinivas/projects'), Path('/home/srinivas/Documents/Codex')]


def auth_status():
    result = subprocess.run([str(CLAUDE), 'auth', 'status'], capture_output=True, text=True, timeout=20)
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return {'loggedIn': False, 'error': 'Unable to read Claude authentication status'}
    return {k: data.get(k) for k in ('loggedIn', 'authMethod', 'apiProvider')}


def job_dir(job_id):
    if str(uuid.UUID(job_id)) != job_id:
        raise ValueError('Invalid job identifier')
    directory = JOBS / job_id
    if not directory.is_dir():
        raise ValueError('Unknown job')
    return directory


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def worker(directory):
    request = json.loads((directory / 'request.json').read_text())
    tools = 'Read,Glob,Grep' if request['mode'] == 'review' else 'Read,Glob,Grep,Edit,Write'
    command = [str(CLAUDE), '-p', '--output-format', 'json',
               '--strict-mcp-config', '--mcp-config', str(BASE / 'empty-mcp.json'),
               '--tools', tools, '--allowedTools', tools,
               '--permission-mode', 'default' if request['mode'] == 'review' else 'acceptEdits',
               '--setting-sources', '', '--disable-slash-commands',
               '--append-system-prompt',
               'You are a delegated worker. Stay within the assigned work package. '
               'Do not commit, push, publish, contact a broker, or change credentials. '
               'Return changed files, rationale, limitations, and suggested test commands. '
               'The supervising agent owns final verification and integration.']
    environment = os.environ.copy()
    environment.pop('CLAUDECODE', None)
    with (directory / 'stdout.json').open('w') as stdout, (directory / 'stderr.log').open('w') as stderr:
        process = subprocess.Popen(command, cwd=request['work_dir'], env=environment,
                                   stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   start_new_session=True, text=True)
        write_json(directory / 'state.json', {'status': 'running', 'pid': process.pid})
        try:
            process.communicate(request['prompt'], timeout=1800)
            status = 'completed' if process.returncode == 0 else 'failed'
            stdout.flush()
            if status == 'completed':
                try:
                    receipt = json.loads((directory / 'stdout.json').read_text())
                    if receipt.get('is_error') or receipt.get('type') != 'result':
                        status = 'failed'
                except (ValueError, AttributeError):
                    status = 'failed'
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            status = 'timed_out'
        write_json(directory / 'state.json', {'status': status, 'exit_code': process.returncode})


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--worker':
    worker(job_dir(sys.argv[2]))
    sys.exit(0)

from mcp.server.fastmcp import FastMCP
mcp = FastMCP('Claude delegation')


@mcp.tool()
def claude_status() -> dict:
    """Check installed Claude CLI and account authentication without exposing credentials."""
    return {'installed': CLAUDE.is_file(), 'authentication': auth_status()}


@mcp.tool()
def claude_start(prompt: str, work_dir: str, mode: str = 'review') -> dict:
    """Delegate explicitly authorized work to Claude. Review is read-only; edit permits file edits.

    Use a separate checkout for edits. No command execution or MCP tools are exposed to Claude.
    Root agent runs tests, reviews diffs and owns commits/pushes. Returns persistent job ID.
    """
    if mode not in ('review', 'edit'):
        raise ValueError('mode must be review or edit')
    path = Path(work_dir).resolve(strict=True)
    if not path.is_dir() or not any(path.is_relative_to(root) for root in ROOTS):
        raise ValueError('Work directory must be under the approved local project roots')
    if not prompt.strip() or len(prompt) > 200000:
        raise ValueError('Prompt must contain 1–200000 characters')
    if not auth_status().get('loggedIn'):
        raise ValueError('Claude CLI needs authentication: run the installed claude auth login')
    JOBS.mkdir(parents=True, exist_ok=True, mode=0o700)
    identifier = str(uuid.uuid4())
    directory = JOBS / identifier
    directory.mkdir(mode=0o700)
    write_json(directory / 'request.json', {'prompt': prompt, 'work_dir': str(path), 'mode': mode})
    write_json(directory / 'state.json', {'status': 'starting'})
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', identifier],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return {'job_id': identifier, 'status': 'starting', 'mode': mode}


@mcp.tool()
def claude_result(job_id: str) -> dict:
    """Read persistent delegated job status and its result; no waiting or duplicate submission."""
    directory = job_dir(job_id)
    state = json.loads((directory / 'state.json').read_text())
    if state['status'] in ('completed', 'failed', 'timed_out'):
        output = directory / 'stdout.json'
        state['output'] = output.read_text()[-60000:] if output.exists() else ''
        state['receipt_directory'] = str(directory)
    return state


@mcp.tool()
def claude_cancel(job_id: str) -> dict:
    """Stop an explicitly identified running Claude job; preserve its audit files."""
    directory = job_dir(job_id)
    state = json.loads((directory / 'state.json').read_text())
    if state['status'] == 'running':
        # Verify ownership before signalling, avoiding a recycled PID.
        try:
            argv = Path(f"/proc/{state['pid']}/cmdline").read_bytes()
            if str(CLAUDE).encode() not in argv:
                raise ValueError('Process identity no longer matches Claude; refusing cancellation')
            os.killpg(state['pid'], signal.SIGTERM)
        except FileNotFoundError:
            return {'status': 'process_exited'}
        return {'status': 'cancellation_requested'}
    return state


if __name__ == '__main__':
    mcp.run(transport='stdio')
