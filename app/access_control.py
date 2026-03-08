"""ACL（访问控制）与工作空间决策模块。

职责：
1) 判定某个企微用户是否允许使用 Agent
2) 为允许用户返回其绑定的独立 workspace 与 agent_id
"""

import json
import os
import re
from dataclasses import dataclass

from app.config import settings


@dataclass
class AccessDecision:
    """访问决策结果。

    - allowed: 是否允许访问
    - workspace_dir: 本次请求应使用的工作空间目录
    - agent_id: 本次请求应使用的隔离 agent
    - reason: 拒绝原因（仅在 denied 时有意义）
    """

    allowed: bool
    workspace_dir: str
    agent_id: str
    reason: str = ''


def _sanitize(raw: str) -> str:
    """清洗用户标识，避免目录名出现危险字符。"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)


def _default_workspace(wecom_user_id: str) -> str:
    """在未显式配置 workspace 时，生成默认工作空间路径。"""
    return os.path.join(settings.openclaw_workspace_root, _sanitize(wecom_user_id))


def _load_acl() -> dict:
    """读取 ACL 文件。

    文件不存在时返回空 users，避免主流程异常中断。
    """
    path = settings.openclaw_acl_file
    if not os.path.exists(path):
        return {'users': {}}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_access(wecom_user_id: str) -> AccessDecision:
    """根据用户ID做访问判定并返回路由目标。

    规则：
    - ACL 关闭：默认允许，使用默认 workspace，agent=main
    - ACL 开启：必须在 users_acl.json 中存在且 enabled=true，且必须配置 agent_id
    """
    # ACL 未开启时，兼容放行（主要用于开发/迁移阶段）
    if not settings.openclaw_acl_enabled:
        ws = _default_workspace(wecom_user_id)
        os.makedirs(ws, exist_ok=True)
        return AccessDecision(allowed=True, workspace_dir=ws, agent_id='main')

    acl = _load_acl()
    users = acl.get('users', {}) if isinstance(acl, dict) else {}
    item = users.get(wecom_user_id)

    # 不在白名单
    if not item:
        return AccessDecision(allowed=False, workspace_dir='', agent_id='', reason='not_allowlisted')

    # 白名单中但禁用
    enabled = bool(item.get('enabled', True))
    if not enabled:
        return AccessDecision(allowed=False, workspace_dir='', agent_id='', reason='disabled')

    # 解析用户专属 workspace 与 agent_id
    workspace_dir = item.get('workspace') or _default_workspace(wecom_user_id)
    agent_id = item.get('agent_id', '')
    if not agent_id:
        return AccessDecision(allowed=False, workspace_dir='', agent_id='', reason='missing_agent_id')

    # 保障目录存在
    os.makedirs(workspace_dir, exist_ok=True)
    return AccessDecision(allowed=True, workspace_dir=workspace_dir, agent_id=agent_id)
