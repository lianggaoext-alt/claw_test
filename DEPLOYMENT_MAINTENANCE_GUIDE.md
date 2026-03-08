# WeCom ↔ OpenClaw 桥接服务部署与维护说明

本文档记录当前项目在服务器上的部署结构、运行方式、更新步骤、故障排查与日常维护操作。

---

## 1. 项目与部署位置

- 项目目录：`/root/.openclaw/workspace`
- 代码目录：`/root/.openclaw/workspace/app`
- 环境配置文件：`/root/.openclaw/workspace/.env`
- Python 虚拟环境：`/root/.openclaw/workspace/.venv`

### 运行服务（systemd）

- 服务名：`wecom-openclaw-bridge`
- Service 文件：`/etc/systemd/system/wecom-openclaw-bridge.service`

### Nginx 反向代理

- Nginx vhost 配置：`/www/server/panel/vhost/nginx/wecom-openclaw-bridge.conf`
- 已配置域名：`dsai.dansewudao.com`
- 已监听端口：`80`、`7090`
- 回调入口：`/reply`（转发到后端 `/wecom/callback`）

---

## 2. 当前回调地址

企业微信后台“接收消息服务器配置”使用：

`http://dsai.dansewudao.com:7090/reply?agid=1000211`

> 说明：后端实际处理路径是 `/wecom/callback`，Nginx 已做路径映射。

---

## 3. 配置项说明（.env）

文件：`/root/.openclaw/workspace/.env`

核心参数：

- `WECOM_TOKEN`：企微回调 Token
- `WECOM_ENCODING_AES_KEY`：企微回调 AES Key（43位）
- `WECOM_CORP_ID`：企业 ID
- `WECOM_AGENT_ID`：应用 AgentID
- `WECOM_SECRET`：应用 Secret（用于主动发送消息 API）

OpenClaw 相关：

- `OPENCLAW_CLI_PATH`：默认 `openclaw`
- `OPENCLAW_TIMEOUT_SECONDS`：当前 `60`
- `OPENCLAW_SESSION_PREFIX`：当前 `wecom_`

会话映射规则：

- 每个企微用户固定一个 OpenClaw 会话：`wecom_<FromUserName>`

---

## 4. 服务架构说明

当前实现为“双通道回复”：

1. **被动回调快速回复**（避免企微回调超时）
2. **后台异步调用 OpenClaw**
3. **通过企微 API 主动发送最终回复**（依赖 `WECOM_SECRET`）

这样可显著降低“偶发不回消息”的问题。

---

## 5. 日常操作命令

以下命令在服务器执行。

### 5.1 服务状态与重启

```bash
systemctl status wecom-openclaw-bridge --no-pager -l
systemctl restart wecom-openclaw-bridge
systemctl stop wecom-openclaw-bridge
systemctl start wecom-openclaw-bridge
```

### 5.2 查看运行日志

```bash
journalctl -u wecom-openclaw-bridge -f
journalctl -u wecom-openclaw-bridge -n 200 --no-pager
```

### 5.3 Nginx 配置测试与重载

```bash
nginx -t
systemctl reload nginx
```

### 5.4 快速健康检查

```bash
curl -i http://dsai.dansewudao.com:7090/healthz
```

预期：HTTP 200，返回 `{"status":"ok"}`。

---

## 6. 代码更新与部署流程（推荐）

### 6.1 更新代码

```bash
cd /root/.openclaw/workspace
git fetch --all --prune
git checkout feature/wecom-openclaw-bridge
git pull --ff-only
```

> 若已合并到 `main`，则改为 `git checkout main && git pull --ff-only`。

### 6.2 安装/更新依赖

```bash
cd /root/.openclaw/workspace
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.3 重启服务

```bash
systemctl restart wecom-openclaw-bridge
systemctl status wecom-openclaw-bridge --no-pager -l
```

### 6.4 验证

```bash
curl -i http://dsai.dansewudao.com:7090/healthz
journalctl -u wecom-openclaw-bridge -n 50 --no-pager
```

---

## 7. 常见问题排查

### 7.1 回调验证失败（401 / signature mismatch）

排查：

- `WECOM_TOKEN` 是否与企微后台一致
- `WECOM_ENCODING_AES_KEY` 是否一致
- `WECOM_CORP_ID` 是否正确
- 修改后是否重启服务

### 7.2 企微发消息后不回

先看日志是否收到 POST：

```bash
journalctl -u wecom-openclaw-bridge -n 200 --no-pager
```

若有 `POST /wecom/callback ... 200 OK` 但前端无消息：

- 检查 `WECOM_AGENT_ID` 是否正确
- 检查 `WECOM_SECRET` 是否正确（主动发送需要）
- 检查应用可见范围是否包含发送人
- 检查 `OPENCLAW_TIMEOUT_SECONDS` 是否过小

### 7.3 域名可访问但端口不通

- 检查安全组/防火墙是否放行 `7090`
- 检查 Nginx 是否监听该端口
- 检查 Nginx 配置是否 reload 成功

---

## 8. 关键文件清单

- `/root/.openclaw/workspace/app/main.py`
- `/root/.openclaw/workspace/app/openclaw_bridge.py`
- `/root/.openclaw/workspace/app/wecom_api.py`
- `/root/.openclaw/workspace/app/config.py`
- `/root/.openclaw/workspace/.env`
- `/etc/systemd/system/wecom-openclaw-bridge.service`
- `/www/server/panel/vhost/nginx/wecom-openclaw-bridge.conf`

---

## 9. 安全建议

- 定期轮换：`WECOM_SECRET`、`WECOM_TOKEN`、`WECOM_ENCODING_AES_KEY`
- 不要把 `.env` 提交到 Git
- 生产建议启用 HTTPS 回调地址
- 变更配置后务必重启服务并做健康检查

---

最后更新时间：自动生成于当前服务器环境
