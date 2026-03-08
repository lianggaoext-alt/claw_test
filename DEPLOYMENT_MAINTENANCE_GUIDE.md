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
- Cron 回推入口：`/cron/deliver`（用于 wecom agent 定时任务结果回推）

---

## 2. 当前回调地址

- 企业微信回调：`http://dsai.dansewudao.com:7090/reply?agid=1000211`
- Cron 回推 webhook：`http://dsai.dansewudao.com:7090/cron/deliver`
  - Header: `X-Cron-Token: <CRON_WEBHOOK_TOKEN>`


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
- `OPENCLAW_WORKSPACE_ROOT`：每用户独立工作空间根目录
- `OPENCLAW_ACL_ENABLED`：是否启用用户白名单
- `OPENCLAW_ACL_FILE`：白名单文件路径（当前 `/root/.openclaw/workspace/users_acl.json`）
- `OPENCLAW_NO_ACCESS_REPLY`：未开通权限时的回复文案
- `CRON_WEBHOOK_TOKEN`：cron webhook 回调鉴权 token

会话映射规则：

- 每个企微用户固定一个 OpenClaw 会话：`wecom_<FromUserName>`
- 每个企微用户固定一个独立工作空间：`<OPENCLAW_WORKSPACE_ROOT>/<FromUserName>`

---

## 4. 服务架构说明

当前实现为“双通道回复 + 稳定性增强”：

1. **被动回调快速回复**（避免企微回调超时）
2. **后台异步调用 OpenClaw**
3. **通过企微 API 主动发送最终回复**（依赖 `WECOM_SECRET`）
4. **消息去重**（同一消息重复投递只处理一次）
5. **主动推送失败重试**（指数退避）
6. **结构化日志**（便于定位用户、耗时、失败原因）
7. **首次开通欢迎语**（产品体验优化）

这样可显著降低“偶发不回消息”和“重复回复”的问题。

---

## 5. 用户授权（ACL）管理

ACL 文件：`/root/.openclaw/workspace/users_acl.json`

示例结构：

```json
{
  "users": {
    "GaoLiang": {
      "enabled": true,
      "workspace": "/root/.openclaw/wecom-workspaces/GaoLiang",
      "agent_id": "wecom-gaoliang"
    }
  }
}
```

操作步骤：

1. 为用户创建隔离 agent（一次性）

```bash
openclaw agents add wecom-gaoliang \
  --workspace /root/.openclaw/wecom-workspaces/GaoLiang \
  --non-interactive --json
```

2. 编辑 ACL 文件，添加/禁用用户（必须填写 `agent_id`）
3. 确认 `.env` 中 `OPENCLAW_ACL_ENABLED=true`
4. 重启服务生效

```bash
systemctl restart wecom-openclaw-bridge
```

未在 ACL 的用户会收到：`你暂未开通权限，请联系管理员。`

### ACL 用户维护命令清单

#### 查看当前 ACL

```bash
cat /root/.openclaw/workspace/users_acl.json
```

#### 开通新用户（示例：Alice）

```bash
# 1) 创建独立 workspace
mkdir -p /root/.openclaw/wecom-workspaces/Alice

# 2) 创建独立 agent
openclaw agents add wecom-alice \
  --workspace /root/.openclaw/wecom-workspaces/Alice \
  --non-interactive --json

# 3) 编辑 ACL，添加用户条目（enabled/workspace/agent_id）
vi /root/.openclaw/workspace/users_acl.json

# 4) 重启服务
systemctl restart wecom-openclaw-bridge
```

#### 禁用用户（保留数据）

```bash
# 将该用户 enabled 改为 false
vi /root/.openclaw/workspace/users_acl.json
systemctl restart wecom-openclaw-bridge
```

#### 删除用户（谨慎）

```bash
# 1) 从 ACL 删除条目
vi /root/.openclaw/workspace/users_acl.json

# 2) 删除独立 agent
openclaw agents delete wecom-alice

# 3) 可选：删除该用户工作空间数据
rm -rf /root/.openclaw/wecom-workspaces/Alice

# 4) 重启服务
systemctl restart wecom-openclaw-bridge
```

#### 检查 ACL 开关状态

```bash
grep OPENCLAW_ACL_ENABLED /root/.openclaw/workspace/.env
```

## 6. 日常操作命令

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

结构化日志关键事件：
- `incoming`：收到消息
- `duplicate_dropped`：重复消息被去重
- `push_send_ok` / `push_send_fail`：主动推送结果
- `process_done`：处理完成（含耗时）

示例筛选：

```bash
journalctl -u wecom-openclaw-bridge -n 300 --no-pager | grep '"event":"push_send_fail"'
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

## 10. 对话命令索引

日常通过助手维护用户，请参考：

- `/root/.openclaw/workspace/COMMAND_INDEX.md`

最后更新时间：自动生成于当前服务器环境
