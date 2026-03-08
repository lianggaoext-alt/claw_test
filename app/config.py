from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    wecom_token: str
    wecom_encoding_aes_key: str
    wecom_corp_id: str
    wecom_agent_id: int
    wecom_secret: str

    # OpenClaw bridge settings
    openclaw_cli_path: str = 'openclaw'
    openclaw_timeout_seconds: int = 60
    openclaw_session_prefix: str = 'wecom_'
    openclaw_workspace_root: str = '/root/.openclaw/wecom-workspaces'
    openclaw_acl_enabled: bool = False
    openclaw_acl_file: str = '/root/.openclaw/workspace/users_acl.json'
    openclaw_no_access_reply: str = '你暂未开通权限，请联系管理员。'

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


settings = Settings()
