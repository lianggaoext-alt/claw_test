"""应用配置定义。

通过 pydantic-settings 从 `.env` 读取配置，所有配置项集中在这里，
避免在业务代码中散落硬编码常量。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ========== 企业微信基础配置 ==========
    # 回调校验 Token（企微后台与本服务保持一致）
    wecom_token: str
    # 回调加解密 AES Key（43位）
    wecom_encoding_aes_key: str
    # 企业 CorpID
    wecom_corp_id: str
    # 自建应用 AgentID（用于主动发消息）
    wecom_agent_id: int
    # 自建应用 Secret（用于换取 access_token）
    wecom_secret: str

    # ========== OpenClaw 桥接配置 ==========
    # OpenClaw CLI 命令路径
    openclaw_cli_path: str = 'openclaw'
    # 调用 OpenClaw 的超时秒数（用于防止长时间阻塞）
    openclaw_timeout_seconds: int = 60
    # 会话 ID 前缀，最终会形成 `wecom_<userid>`
    openclaw_session_prefix: str = 'wecom_'
    # 每个企微用户独立工作空间的根目录
    openclaw_workspace_root: str = '/root/.openclaw/wecom-workspaces'
    # 是否启用 ACL 白名单控制
    openclaw_acl_enabled: bool = False
    # ACL 文件路径（JSON）
    openclaw_acl_file: str = '/root/.openclaw/workspace/users_acl.json'
    # 未开通用户的默认回复文案
    openclaw_no_access_reply: str = '你暂未开通权限，请联系管理员。'

    # Cron webhook 回调鉴权 token（用于把定时任务结果转发给企微用户）
    cron_webhook_token: str = ''

    # 指定 `.env` 作为配置来源；忽略未声明的额外字段
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


# 全局单例配置对象
settings = Settings()
