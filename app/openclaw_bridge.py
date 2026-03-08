import json
import re
import subprocess
import time

from app.config import settings


class OpenClawBridgeError(Exception):
    pass


def _sanitize_session_part(raw: str) -> str:
    # Keep session ids deterministic and safe for CLI/storage.
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)


def session_id_for_wecom_user(wecom_user_id: str) -> str:
    return f"{settings.openclaw_session_prefix}{_sanitize_session_part(wecom_user_id)}"


def ask_openclaw(wecom_user_id: str, message: str, workspace_dir: str, agent_id: str) -> str:
    session_id = session_id_for_wecom_user(wecom_user_id)
    cmd = [
        settings.openclaw_cli_path,
        'agent',
        '--agent',
        agent_id,
        '--session-id',
        session_id,
        '--message',
        message,
        '--json',
        '--timeout',
        str(settings.openclaw_timeout_seconds),
    ]

    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.openclaw_timeout_seconds + 1,
            check=False,
            cwd=workspace_dir,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpenClawBridgeError('openclaw timeout (>5s), fallback reply used') from exc

    _elapsed = time.time() - started

    if proc.returncode != 0:
        raise OpenClawBridgeError(f'openclaw failed: {proc.stderr.strip() or proc.stdout.strip()}')

    try:
        data = json.loads(proc.stdout)
        payloads = data.get('result', {}).get('payloads', [])
        if payloads and payloads[0].get('text'):
            return payloads[0]['text']
        raise OpenClawBridgeError('openclaw returned empty payload')
    except json.JSONDecodeError as exc:
        raise OpenClawBridgeError(f'invalid openclaw json output: {proc.stdout[:200]}') from exc
