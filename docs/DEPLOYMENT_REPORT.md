# Anti-Bagu Cloud Beta 部署报告

日期：2026-08-22

服务器：`101.42.92.125`

入口：`https://101.42.92.125`

## 生产组件

- Nginx 1.24：HTTPS、WSS、React SPA 和 Agent 下载。
- FastAPI：`127.0.0.1:8765`，单 Uvicorn worker。
- PostgreSQL 16：用户、会话、任务、事件和平台审计。
- 本地任务存储：`/var/lib/anti-bagu/storage`。
- systemd：应用、证书续期和每日备份。

## 验证结果

- 公网 HTTPS、证书链和安全响应头：通过。
- Web 登录、注册、任务创建和预检保护：通过。
- 公网 Agent WSS、任务 UI WSS、手机 WSS：通过。
- macOS Agent 下载及 SHA-256：通过。
- PostgreSQL 迁移和任务事件持久化：通过。
- Let’s Encrypt IP 证书续期 dry-run：通过。
- PostgreSQL、任务事件、日志和音频备份校验：通过。
- 自动化：40 个 Python 测试、3 个 Swift 测试、Ruff、TypeScript/Vite、`git diff --check` 全部通过。

## 凭据

初始管理员用户名是 `admin`。密码未写入仓库，已保存在当前 Mac 的系统钥匙串：

```bash
security find-generic-password -w -a admin -s cn.anti-bagu.server-admin
```

## 尚未执行的付费链路

服务器没有平台级模型 Key。正式 ASR/LLM 调用必须由真实用户在 macOS Agent 中配置自己的 Key 后，通过任务预检触发。因此部署验收覆盖了 Key 缺失时的安全失败和整条公网通信链路，但没有消耗用户模型额度运行真实音频识别。
