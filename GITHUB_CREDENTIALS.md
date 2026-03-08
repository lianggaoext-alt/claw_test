# GitHub 凭证与访问信息记录

> 用途：记录本机与 `lianggaoext-alt/claw_test` 相关的连接信息，便于后续查阅。
> 安全建议：不要在此文件保存明文密码、PAT Token、私钥全文。

## 1) 账号与仓库

- GitHub 用户名：`lianggaoext-alt`
- 绑定邮箱：`liang.gao.ext@gmail.com`
- 仓库（HTTPS）：`https://github.com/lianggaoext-alt/claw_test`
- 仓库（SSH）：`git@github.com:lianggaoext-alt/claw_test.git`
- 默认分支策略：`main + feature/*`
- 已推送分支：
  - `main`
  - `feature/init`

## 2) 本机 Git 配置（当前仓库）

- `git config user.name` = `lianggaoext-alt`
- `git config user.email` = `liang.gao.ext@gmail.com`
- `remote origin` = `git@github.com:lianggaoext-alt/claw_test.git`

## 3) SSH 认证配置（本机）

- SSH 配置文件：`~/.ssh/config`
- Host：`github.com`
- IdentityFile：`~/.ssh/id_ed25519_github`
- 公钥文件：`~/.ssh/id_ed25519_github.pub`
- 当前公钥指纹（SHA256）：`lkLaqdd+KaM3FLQ/PkRvDywOiaIQEVCB2log+GEZ/0k`
- GitHub Key Type：`Authentication Key`

## 4) 常用命令速查

```bash
# 测试 GitHub SSH
ssh -T git@github.com

# 查看远程
git remote -v

# 新建功能分支
git checkout -b feature/<name>

# 提交并推送
git add .
git commit -m "feat: ..."
git push -u origin feature/<name>

# 同步主分支
git checkout main
git pull --rebase origin main
```

## 5) 凭证记录模板（建议用占位符）

> 建议把真实敏感信息放到密码管理器；这里只放“位置/备注”。

- PAT Token：`[已存于密码管理器：________]`
- Token 权限范围：`[repo / workflow / ...]`
- 到期时间：`[YYYY-MM-DD]`
- 2FA 方式：`[TOTP / 短信 / 安全密钥]`
- 恢复码位置：`[密码管理器条目名]`

---

最后更新：由 OpenClaw 助手自动生成（用于后续查阅）
