# Lark Test Ledger

面向 Codex 与测试团队的 Lark Base 测试用例账本工具。它提供统一的需求来源校验、
测试用例 Manifest、同步预览与提交、提测顺序执行、结果回写和失败证据追加能力。

本仓库同时包含：

- 可安装的 Codex Skill（`skill/lark-test-ledger`，发布版本 0.4.0）；
- 可复用的 Python/PowerShell 框架源码（当前框架版本 0.3.0）；
- 单元测试、Manifest Schema、安装脚本和完整配置文档；
- 值全部留空的 `.env.example` 模板。

## 核心能力

- 校验 PRD/需求来源哈希；
- 生成并验证 `lark-test-ledger/v1` Manifest；
- 同步前提供 dry-run，确认后才写入 Lark；
- 用全局唯一的`用例ID`定位记录；
- 使用`提测顺序`标记和排序最小提测集；
- 执行时只更新 `Date`、`Attachment`、`测试结果`和`实际结果/备注`；
- 失败证据追加到原记录，不覆盖已有附件；
- 写入结果和附件后自动回读验证。

## 仓库结构

```text
.
├── skill/lark-test-ledger/          # Codex Skill及打包运行时
├── src/dms_test_ledger/             # 完整Python源码
├── tests/                           # 单元测试
├── schema/                          # Manifest JSON Schema
├── COMPANY_SETUP_GUIDE.md           # 公司级完整配置手册
├── QUICKSTART.md                    # 快速安装与日常使用
├── SECURITY.md                      # 凭据、OAuth与数据安全边界
├── Install-LarkTestLedgerSkill.ps1  # 安装用户级Codex Skill
├── Uninstall-LarkTestLedgerSkill.ps1
├── Setup-LarkTestProject.ps1        # 框架项目向导
├── Initialize-LarkTestProject.ps1   # 手工初始化备用入口
├── identity.env.example             # 个人身份模板，所有值为空
└── project.env.example              # 项目配置模板，所有值为空
```

## 环境要求

- Windows 10/11；
- PowerShell 7；
- Python 3.11 或更高版本；
- Lark 自建应用；
- 对目标 Wiki/Base 的访问和编辑权限。

## 快速安装 Skill

在 PowerShell 7 中运行：

```powershell
& '.\Install-LarkTestLedgerSkill.ps1'
```

安装完成后重新启动 Codex。入口：

- Codex CLI/IDE：`$lark-test-ledger`
- ChatGPT 桌面端：`@Lark 测试账本`

完整步骤见 [QUICKSTART.md](QUICKSTART.md) 和
[COMPANY_SETUP_GUIDE.md](COMPANY_SETUP_GUIDE.md)。

## 配置模型

配置分为两层：

1. 个人/电脑身份配置：App ID、App Secret、OAuth token 数据库和刷新锁；
2. 项目配置：目标 Base URL、表名、本地状态库和 Manifest 归档目录。

项目配置只引用个人身份配置，不复制 App Secret 或 token。仓库中的示例环境文件所有值
均为空；请复制后只在本机填写，不要提交真实 `.env`。

## 常用命令

使用 Skill：

```powershell
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' doctor
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' case list --submission-only
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' execution next
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' sync '.\cases\manifest.json'
```

使用项目启动器：

```powershell
./.lark-test-ledger/lark-ledger.ps1 doctor
./.lark-test-ledger/lark-ledger.ps1 case list --submission-only
./.lark-test-ledger/lark-ledger.ps1 execution next
```

## 安全

严禁提交或分发：

- 真实 App Secret；
- access token、refresh token；
- `identity.env`、`ledger.env`；
- OAuth SQLite、WAL、SHM或其他凭据数据库；
- 真实测试证据、Manifest归档和执行缓存。

每位测试人员应使用自己的公司账号完成 OAuth。不要在不同电脑之间复制个人 token
数据库。详细规则见 [SECURITY.md](SECURITY.md)。

## 版本说明

- Skill：0.4.0
- Framework/source：0.3.0
- Manifest Schema：`lark-test-ledger/v1`
- 兼容旧 Schema：`dms-test-ledger/v1`

当前仓库尚未声明开源许可证。在许可证确定前，代码版权和再分发权利默认保留。
