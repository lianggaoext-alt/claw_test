# 企业微信自建应用回调服务（Python）

这个服务基于 FastAPI，提供企业微信自建应用回调所需的能力：

- URL 校验（`GET /wecom/callback`）
- 接收企业微信加密消息（`POST /wecom/callback`）
- 自动回消息（当前支持文本回文本，其它类型回提示）
- 健康检查（`GET /healthz`）

## 1. 配置

复制配置模板：

```bash
cp .env.example .env
```

填写 `.env`：

- `WECOM_TOKEN`：回调配置中的 Token
- `WECOM_ENCODING_AES_KEY`：回调配置中的 EncodingAESKey
- `WECOM_CORP_ID`：企业 ID（`ww...`）
- `WECOM_AGENT_ID`：应用 AgentId（当前预留）

## 2. 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3. 公网部署（Docker）

```bash
docker build -t wecom-callback:latest .
docker run -d --name wecom-callback \
  --env-file .env \
  -p 8000:8000 \
  wecom-callback:latest
```

建议用 Nginx/云负载均衡反向代理到 `8000`，并配置 HTTPS。企业微信回调地址示例：

```
https://your-domain.com/wecom/callback
```

## 4. 企业微信后台配置

在应用设置中填写：

- 接收消息服务器配置 URL：`https://your-domain.com/wecom/callback`
- Token：与 `.env` 一致
- EncodingAESKey：与 `.env` 一致
- 数据加密方式：**安全模式**

保存后企业微信会发起 URL 校验请求，服务会自动解密 `echostr` 并返回明文。

## 5. 行为说明

- 收到文本消息：回复 `已收到你的消息：{内容}`
- 收到非文本消息：回复 `已收到 {类型} 类型消息，当前仅自动回文本。`

## 6. 后续可扩展

- 增加主动发消息接口（`/message/send`）
- 增加 access_token 缓存（内存/Redis）
- 增加签名失败告警与结构化日志
