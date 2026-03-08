# 企业微信自建应用 ↔ OpenClaw 桥接服务

这个服务基于 FastAPI，提供企业微信自建应用回调并把文本消息转发到 OpenClaw：

- URL 校验（`GET /wecom/callback`）
- 接收企业微信加密消息（`POST /wecom/callback`）
- 企业微信用户固定映射到 OpenClaw 会话（`wecom_<FromUserName>`）
- 被动回调快速应答（避免超时）+ 主动发送 OpenClaw 最终回复
- 健康检查（`GET /healthz`）

## 1) 配置

```bash
cp .env.example .env
```

填写 `.env`：

- `WECOM_TOKEN`：企业微信回调 Token
- `WECOM_ENCODING_AES_KEY`：企业微信回调 EncodingAESKey（43 位）
- `WECOM_CORP_ID`：企业 ID（`ww...`）
- `WECOM_AGENT_ID`：应用 AgentId
- `WECOM_SECRET`：应用 Secret（用于后续主动调用企业微信 API）

OpenClaw 桥接相关：

- `OPENCLAW_CLI_PATH`：默认 `openclaw`
- `OPENCLAW_TIMEOUT_SECONDS`：默认 `60`
- `OPENCLAW_SESSION_PREFIX`：默认 `wecom_`
- `OPENCLAW_WORKSPACE_ROOT`：每个企微用户独立工作空间根目录
- `OPENCLAW_ACL_ENABLED`：是否启用白名单（true/false）
- `OPENCLAW_ACL_FILE`：白名单文件路径（JSON）
- `OPENCLAW_NO_ACCESS_REPLY`：未开通用户的回复文案

## 2) 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3) 企业微信后台配置

在自建应用中配置：

- 接收消息服务器 URL：`https://your-domain.com/wecom/callback`
- Token：与 `.env` 一致
- EncodingAESKey：与 `.env` 一致
- 数据加密方式：**安全模式**

> 企业微信保存时会发起 URL 校验。服务会验签并解密 `echostr` 后返回明文。

## 4) 会话映射与权限控制

- 企业微信 `FromUserName` → OpenClaw `session-id`
- 规则：`{OPENCLAW_SESSION_PREFIX}{FromUserName}`（特殊字符会自动替换成 `_`）
- 每个用户独立 workspace：`{OPENCLAW_WORKSPACE_ROOT}/{FromUserName}`
- 启用白名单后，仅 `users_acl.json` 中的用户可用
- 未授权用户会收到：`OPENCLAW_NO_ACCESS_REPLY`

示例：
- `zhangsan` → `wecom_zhangsan`

## 5) Docker（可选）

```bash
docker build -t wecom-openclaw-bridge:latest .
docker run -d --name wecom-openclaw-bridge \
  --env-file .env \
  -p 8000:8000 \
  wecom-openclaw-bridge:latest
```
