from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    wecom_token: str
    wecom_encoding_aes_key: str
    wecom_corp_id: str
    wecom_agent_id: int

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


settings = Settings()
