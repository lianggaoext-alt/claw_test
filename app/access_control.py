import json
import os
import re
from dataclasses import dataclass

from app.config import settings


@dataclass
class AccessDecision:
    allowed: bool
    workspace_dir: str
    reason: str = ''


def _sanitize(raw: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)


def _default_workspace(wecom_user_id: str) -> str:
    return os.path.join(settings.openclaw_workspace_root, _sanitize(wecom_user_id))


def _load_acl() -> dict:
    path = settings.openclaw_acl_file
    if not os.path.exists(path):
        return {'users': {}}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_access(wecom_user_id: str) -> AccessDecision:
    if not settings.openclaw_acl_enabled:
        ws = _default_workspace(wecom_user_id)
        os.makedirs(ws, exist_ok=True)
        return AccessDecision(allowed=True, workspace_dir=ws)

    acl = _load_acl()
    users = acl.get('users', {}) if isinstance(acl, dict) else {}
    item = users.get(wecom_user_id)
    if not item:
        return AccessDecision(allowed=False, workspace_dir='', reason='not_allowlisted')

    enabled = bool(item.get('enabled', True))
    if not enabled:
        return AccessDecision(allowed=False, workspace_dir='', reason='disabled')

    workspace_dir = item.get('workspace') or _default_workspace(wecom_user_id)
    os.makedirs(workspace_dir, exist_ok=True)
    return AccessDecision(allowed=True, workspace_dir=workspace_dir)
