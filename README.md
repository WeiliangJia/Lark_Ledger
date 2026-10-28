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

## 推荐：统一初始化入口

在 Windows 的 PowerShell 7 中，从仓库根目录运行：

```powershell
./Start-LarkTestLedger.ps1 -ProjectRoot 'D:\Projects\ProjectA'
```

向导检查 Python 3.11+，选择 Codex / Claude Code / Qoder，安装 Skill，复用或创建本机身份，
引导浏览器 OAuth，最后只读检查 Base 和字段。不会自动创建 Base 或修改字段。
缺少依赖时给出安装建议，不会自动安装系统软件。项目目录须已存在。

- `-CheckOnly`：只检查本机环境，不写配置、不授权。
- `-Client Codex|ClaudeCode|Qoder`：直接选择客户端。
- `-IdentityEnv <路径>`：引用已有身份。
- 重复运行保留已安装 Skill 和项目配置，不自动升级或切换 Base。
- 客户端加载受其版本和权限设置影响；Qoder 图形界面可从 Extensions → Skills 导入整个 Skill 文件夹。
- 当前提供标准目录适配，尚未完成 Claude Code / Qoder 图形界面端到端验证。
- `doctor` 非零退出码表示未就绪；字段异常先运行 `schema plan` 查看差异。

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

本项目采用 [MIT License](LICENSE)，允许个人和商业使用、修改与分发；分发时须保留版权及许可声明。软件按原样提供，不作担保。
