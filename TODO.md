# TODO / 迭代计划

## 未来迭代（已确认）

### 系统级硬隔离（非 root 运行 + sandbox/container）
目标：把当前“应用层隔离”升级为“系统级隔离”，降低越权风险。

范围：
1. 非 root 运行
   - bridge 服务改为低权限系统用户运行
   - 收紧 systemd 权限（NoNewPrivileges / ProtectSystem / ProtectHome 等）
2. sandbox 隔离
   - 限制可访问目录、系统调用和网络出口
3. container 隔离（生产推荐）
   - 每用户独立容器或独立运行实例
   - 仅挂载用户自己的 workspace

验收标准：
- 授权用户无法访问 `/root/.openclaw/workspace` 等非授权目录
- 未授权用户继续收到“你暂未开通权限，请联系管理员。”
- 现有企微消息收发链路保持可用

---

## 交互约定
- 用户输入：`todo`
- 助手行为：返回当前待办的“简报版进展/计划”
