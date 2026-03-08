"""OpenClaw 调用桥接模块。

该模块负责把“企微来的文本消息”转为一次 OpenClaw CLI 调用，
并返回模型文本结果。
"""

import json
import re
import subprocess
import time

from app.config import settings


class OpenClawBridgeError(Exception):
    """OpenClaw 调用失败或结果异常。"""


def _sanitize_session_part(raw: str) -> str:
    """清洗 session 片段，保证会话ID稳定且安全。"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)


def session_id_for_wecom_user(wecom_user_id: str) -> str:
    """生成用户固定会话ID（实现“每用户独立会话”）。"""
    return f"{settings.openclaw_session_prefix}{_sanitize_session_part(wecom_user_id)}"


def ask_openclaw(wecom_user_id: str, message: str, workspace_dir: str, agent_id: str) -> str:
    """调用 OpenClaw 并返回首条文本回复。

    参数说明：
    - wecom_user_id: 企微用户ID（用于固定 session）
    - message: 用户输入文本
    - workspace_dir: 本次调用的工作目录（用户隔离目录）
    - agent_id: 本次调用使用的隔离 agent
    """
    session_id = session_id_for_wecom_user(wecom_user_id)

    # 构造 CLI 命令：指定 agent + session，保证上下文与工作区都固定
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
        # 在用户独立 workspace 中执行；避免默认落到主 workspace
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

    _elapsed = time.time() - started  # 预留性能统计使用

    if proc.returncode != 0:
        raise OpenClawBridgeError(f'openclaw failed: {proc.stderr.strip() or proc.stdout.strip()}')

    # 解析 JSON 输出，优先拿 result.payloads[0].text
    try:
        data = json.loads(proc.stdout)
        payloads = data.get('result', {}).get('payloads', [])
        if payloads and payloads[0].get('text'):
            return payloads[0]['text']
        raise OpenClawBridgeError('openclaw returned empty payload')
    except json.JSONDecodeError as exc:
        raise OpenClawBridgeError(f'invalid openclaw json output: {proc.stdout[:200]}') from exc
