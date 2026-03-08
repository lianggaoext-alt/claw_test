from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    wecom_token: str
    wecom_encoding_aes_key: str
    wecom_corp_id: str
    wecom_agent_id: int

    # OpenClaw bridge settings
    openclaw_cli_path: str = 'openclaw'
    openclaw_timeout_seconds: int = 60
    openclaw_session_prefix: str = 'wecom_'

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


settings = Settings()
