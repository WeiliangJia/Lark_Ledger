# 安全边界

## 不进入分发包的内容

- `LARK_APP_SECRET` 的真实值；
- access token、refresh token 或包含它们的 SQLite/WAL/SHM 文件；
- 项目 `ledger.env`、截图、Manifest 归档和执行结果缓存；
- 当前用户的本机路径或 Lark Base 私有标识。

仓库只允许提交值为空的`*.env.example`。真实`.env`、`.local`、`.lark-test-ledger`、
SQLite、token、证据目录和Manifest归档均由`.gitignore`排除。提交前仍应执行敏感信息扫描，
不能只依赖文件名。

## 身份复用规则

同一台受控电脑可以让多个项目引用同一个私有 `identity.env`、OAuth token SQLite
和刷新锁。不要复制 token SQLite 形成多个独立副本：refresh token 轮换会使副本
失效，并可能造成并发刷新冲突。

不同测试人员应使用同一个企业自建 App、各自的私有身份配置和各自公司账号完成
OAuth。这样 Lark 的访问权限、撤销和审计仍然对应实际人员。

如果组织明确要求多人使用同一个服务身份，应由运维提供集中凭据代理、权限控制和
审计，不应通过聊天、代码仓库、共享网盘或压缩包分发个人 App Secret/token 数据库。

## 项目权限

能否访问某个 Base 同时取决于 App 权限范围、OAuth 用户权限以及目标 Wiki/Base 的
成员权限。新项目应遵循最小权限原则，并在写入前先执行 `schema plan` 和同步 dry-run。

## 报告安全问题

不要在公开Issue中粘贴App Secret、token、真实Base URL、客户数据或失败截图。请通过仓库
维护者提供的私有渠道报告，并立即撤销泄露的OAuth授权、轮换相关密钥。
