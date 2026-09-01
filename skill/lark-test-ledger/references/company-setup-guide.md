# 公司内部：Codex × Lark 测试账本完整配置手册

本文面向第一次配置的测试人员、项目负责人和 Lark 自建应用管理员。完成后，Codex
可以在项目内读取需求、生成测试用例、同步到 Lark 多维表格、按顺序执行用例，并把
结果和失败证据回写到同一条记录。

## 1. 最终使用效果

配置完成后，每个项目都有一个统一入口：

```powershell
./.lark-test-ledger/lark-ledger.ps1 doctor
./.lark-test-ledger/lark-ledger.ps1 case list --submission-only
./.lark-test-ledger/lark-ledger.ps1 execution next
```

配置分成两层：

- **个人/电脑身份配置**：App ID、App Secret、OAuth token 库和刷新锁；一台电脑只配一次。
- **项目配置**：项目 Base URL、表名、本地状态库和 Manifest 归档；每个项目一份。

项目配置只引用身份配置，不复制 App Secret 和 token。

## 2. 三种使用场景

### 场景 A：同一受控电脑复用已有公司身份

如果电脑已配置Lark Test Ledger身份，可引用现有私有`identity.env`。默认位置为：

```text
C:\Users\<本人>\AppData\Local\LarkTestLedger\identity.env
```

不需要重新输入App ID、App Secret，也通常不需要重新OAuth。不要把该私有文件提交到仓库。

### 场景 B：其他测试人员、其他电脑

使用同一个公司自建 App，但每个人用自己的公司 Lark 账号 OAuth。第一次运行向导时，
需要通过公司批准的密码管理工具取得 App ID/App Secret，或由管理员在测试电脑上预置
身份文件。随后浏览器自动打开，测试人员本人完成 Lark 登录、MFA 和授权确认。

不要把 DMS 当前用户的 token SQLite 复制到其他电脑。

### 场景 C：多人长期使用同一个执行身份

不要分发个人 refresh token。应由运维部署集中式凭据代理或内部测试服务，将 App
Secret/token 保存在服务器端，并提供访问控制和审计。这属于下一阶段的企业化部署，
不是桌面 ZIP 包应承担的凭据共享方式。

## 3. 角色和责任

### Lark App 管理员：一次性工作

1. 维护公司自建 App。
2. 配置回调地址和权限。
3. 发布可用版本并设置可用人员范围。
4. 通过公司密码管理工具提供 App ID/App Secret，或在测试电脑上预置身份文件。

### 项目负责人：每个项目一次

1. 创建或确认项目测试用例 Base。
2. 把目标表共享给执行人员，授予编辑/管理权限。
3. 提供包含 `table=...` 的完整 Base/Wiki URL。
4. 确认是否允许工具创建或补齐测试账本字段。

### 测试人员：每台电脑一次 + 每个项目一次

1. 安装 PowerShell 7 和 Python 3.11+。
2. 运行配置向导。
3. 在自动打开的 Lark 页面中登录和授权。
4. 执行 `doctor` 检查。

## 4. Lark 自建 App 管理员配置

如果公司继续复用当前 DMS 自建 App，管理员只需检查以下项目，无需为每个项目创建
新的 App。

### 4.1 回调地址

在自建 App 的安全设置/OAuth 回调配置中加入并保留：

```text
http://127.0.0.1:8765/callback
```

必须逐字一致，包括协议、IP、端口和路径。测试人员电脑上的 8765 端口应可由本机
Python 临时监听。

### 4.2 App 权限范围

框架的默认 OAuth scopes 为：

```text
offline_access bitable:app wiki:node:read auth:user.id:read
```

用途：

- `offline_access`：保存并刷新用户授权，不要求每天重新登录。
- `bitable:app`：读写多维表格、字段和记录。
- `wiki:node:read`：目标 Base 位于 Wiki/知识空间时解析节点。
- `auth:user.id:read`：读取授权用户标识，支持公司人员字段。

如果还要使用电子表格 API，可由管理员按实际需要增加相关 scope。不要为方便而授予
与测试流程无关的权限。

### 4.3 发布与可用范围

权限修改后，管理员应发布一个公司内部可用版本，并确认需要使用的测试人员属于 App
可用范围。未发布的权限变更通常不会对普通成员生效。

### 4.4 目标 Base 权限

App scope 不等于数据权限。每位 OAuth 用户还必须能访问目标 Wiki/Base：

1. 用户是目标知识空间或页面的成员；
2. 用户对目标表拥有编辑权限；
3. 若需要 `schema apply`，用户还需要管理字段/表结构的权限；
4. Wiki 父页面继承权限时，确认目标节点没有单独收紧权限。

## 5. 测试人员电脑准备

### 5.1 系统要求

- Windows 10/11；
- PowerShell 7；
- Python 3.11 或更高版本；
- 能访问 `open.larksuite.com` 和公司的 Lark 域名；
- 默认浏览器可用。

检查：

```powershell
pwsh --version
python --version
```

### 5.2 获取并校验分发包

取得 `lark-test-ledger-framework-<版本>.zip` 后，管理员应同时提供 SHA-256。

```powershell
Get-FileHash -Algorithm SHA256 `
  -LiteralPath 'C:\Downloads\lark-test-ledger-framework-0.3.0.zip'
```

哈希必须与发布记录完全相同。然后解压：

```powershell
Expand-Archive `
  -LiteralPath 'C:\Downloads\lark-test-ledger-framework-0.3.0.zip' `
  -DestinationPath 'C:\CompanyTools'
```

如果 Windows 阻止脚本运行，可只解除该分发包脚本的下载标记：

```powershell
Get-ChildItem 'C:\CompanyTools\lark-test-ledger-framework-0.3.0' `
  -Filter '*.ps1' | Unblock-File
```

不要关闭全局 PowerShell 安全策略。

## 6. 推荐：一条向导命令完成配置

### 6.1 同一受控电脑复用现有身份

```powershell
& 'C:\CompanyTools\lark-test-ledger-framework-0.3.0\Setup-LarkTestProject.ps1' `
  -ProjectRoot 'D:\Projects\ProjectA' `
  -BaseUrl 'https://company.sg.larksuite.com/wiki/xxx?table=tblxxx&view=vewxxx' `
  -IdentityEnv 'C:\Users\<本人>\AppData\Local\LarkTestLedger\identity.env'
```

### 6.2 其他测试人员第一次配置电脑

```powershell
& 'C:\CompanyTools\lark-test-ledger-framework-0.3.0\Setup-LarkTestProject.ps1' `
  -ProjectRoot 'D:\Projects\ProjectA' `
  -BaseUrl 'https://company.sg.larksuite.com/wiki/xxx?table=tblxxx&view=vewxxx'
```

向导会依次执行：

1. 在 `%LOCALAPPDATA%\LarkTestLedger` 查找个人身份配置；
2. 首次没有配置时，提示输入 App ID；
3. 以隐藏方式提示输入 App Secret；
4. 创建个人 OAuth SQLite 和全电脑共享刷新锁；
5. 在项目中创建 `.lark-test-ledger`、独立状态库和启动器；
6. 为项目创建 `AGENTS.md`；如果已有文件则生成待合并片段，不覆盖原文件；
7. 自动打开 Lark OAuth 页面；
8. 等待用户在浏览器登录、完成 MFA 并确认授权；
9. 自动接收 `127.0.0.1:8765/callback` 回调并保存 token；
10. 自动运行 `doctor`，验证 token、Base 权限、表和 Schema；
11. 自动打开目标 Base，方便人工确认。

如果浏览器未自动打开，终端会打印完整授权 URL，复制到浏览器即可。授权回调默认等待
180 秒；超时后重新运行向导或单独运行 `auth`。

### 6.3 谁输入什么

- **App ID**：首次配置电脑时输入，或由管理员预置。
- **App Secret**：首次配置电脑时在终端隐藏输入；不要发到 Codex 对话或代码仓库。
- **Lark 登录密码/MFA**：只在 Lark 官方浏览器页面输入，脚本和 Codex不会读取。
- **Base URL**：项目负责人提供；必须包含 `table=...`。

## 7. 让 Codex 代为运行向导

可以在目标项目的 Codex 任务中直接说：

```text
请使用公司 Lark 测试账本框架配置当前项目。
框架位于 C:\CompanyTools\lark-test-ledger-framework-0.3.0，
目标 Base 是 https://...?...table=...。
需要我登录或输入敏感信息时暂停让我操作，其余步骤自动完成并运行 doctor。
```

Codex 可以执行本机脚本并触发浏览器打开。若 Codex 沙箱提示批准打开浏览器或访问
项目外的私有 token 文件，请核对路径后批准。账号密码、MFA 和授权确认仍由本人在
浏览器完成。

框架创建的项目 `AGENTS.md` 会让后续 Codex 任务自动遵循同一张账本、执行字段保护和
失败截图规则。OpenAI 官方说明 Codex 会在开始工作前读取项目范围内的 `AGENTS.md`：
https://developers.openai.com/codex/guides/agents-md/

## 8. 首次连接检查

进入项目：

```powershell
Set-Location 'D:\Projects\ProjectA'
./.lark-test-ledger/lark-ledger.ps1 status
./.lark-test-ledger/lark-ledger.ps1 doctor
```

`doctor` 应显示：

```json
{
  "authorized": true,
  "connection_ok": true,
  "target_accessible": true,
  "schema_ready": true,
  "ready": true
}
```

如果 `schema_ready` 为 `false`：

```powershell
./.lark-test-ledger/lark-ledger.ps1 schema plan
```

阅读计划，确认目标确实是测试账本后才运行：

```powershell
./.lark-test-ledger/lark-ledger.ps1 schema apply
./.lark-test-ledger/lark-ledger.ps1 doctor
```

已有业务数据的表不要盲目执行 `schema apply`。字段类型冲突需要人工处理。

## 9. 手工配置备用流程

只有向导无法运行时才使用本节。

### 9.1 创建个人身份文件

复制 `identity.env.example` 到：

```text
C:\Users\<本人>\AppData\Local\LarkTestLedger\identity.env
```

填写 App ID、App Secret、回调地址、token DB 和锁文件绝对路径。

### 9.2 初始化项目

```powershell
& '.\Initialize-LarkTestProject.ps1' `
  -ProjectRoot 'D:\Projects\ProjectA' `
  -BaseUrl 'https://...?...table=tblxxx' `
  -SharedIdentityEnv 'C:\Users\<本人>\AppData\Local\LarkTestLedger\identity.env'
```

### 9.3 OAuth

```powershell
& 'D:\Projects\ProjectA\.lark-test-ledger\lark-ledger.ps1' auth
```

该命令会自动启动浏览器，并在本机等待回调。

### 9.4 检查

```powershell
& 'D:\Projects\ProjectA\.lark-test-ledger\lark-ledger.ps1' doctor
```

## 10. 新建测试账本

优先由项目负责人先在 Lark UI 中创建多维表格并提供完整 URL。若需要 API 创建：

```powershell
./.lark-test-ledger/lark-ledger.ps1 base create --name 'ProjectA 测试用例账本'
```

命令会在授权用户的个人空间创建 Base 并返回 URL。普通 Base API 不能直接把新 Base
创建到指定公共 Wiki 目录；如公司要求放入知识空间，需要在 Lark UI 中移动，然后把
移动后的 Wiki URL 更新到项目 `ledger.env`。

## 11. 日常生成、同步和执行

### 11.1 校验需求来源和 Manifest

```powershell
./.lark-test-ledger/lark-ledger.ps1 hash-source './requirements/PRD.md'
./.lark-test-ledger/lark-ledger.ps1 validate './cases/manifest.json' --verify-sources
```

### 11.2 同步前预览

```powershell
./.lark-test-ledger/lark-ledger.ps1 sync './cases/manifest.json'
```

确认差异后写入：

```powershell
./.lark-test-ledger/lark-ledger.ps1 sync './cases/manifest.json' --commit
```

### 11.3 读取和执行

```powershell
./.lark-test-ledger/lark-ledger.ps1 case list --submission-only
./.lark-test-ledger/lark-ledger.ps1 execution next
```

通过：

```powershell
./.lark-test-ledger/lark-ledger.ps1 execution record `
  --case-id 'PROJECTA-TC-001' --result passed --notes '符合预期'
```

失败并追加截图：

```powershell
./.lark-test-ledger/lark-ledger.ps1 execution record `
  --case-id 'PROJECTA-TC-002' --result failed `
  --notes '提交后出现500' --evidence '.\evidence\PROJECTA-TC-002.png'
```

## 12. 常见错误排查

### 浏览器没有打开

- 使用终端打印的备用 URL；
- 检查默认浏览器关联；
- 检查安全软件是否阻止 Python 启动浏览器。

### `callback timed out` 或 `state mismatch`

- 在 180 秒内完成登录；
- 确认回调地址是 `http://127.0.0.1:8765/callback`；
- 检查 8765 端口是否被占用；
- 不要重复使用旧的授权 URL，重新执行 `auth`。

检查端口：

```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
```

### `No Lark OAuth token found`

```powershell
./.lark-test-ledger/lark-ledger.ps1 auth
```

### refresh token 失效

重新执行 `auth`。不要从另一台电脑复制旧 SQLite 覆盖当前文件。

### Base/Wiki 无权限

- 确认登录的是正确公司账号；
- 请项目负责人将该用户加入 Wiki/Base；
- 确认拥有编辑权限；
- 确认自建 App 已发布且该用户属于可用范围。

### Schema 不完整

先运行 `schema plan`。只有明确知道目标是测试账本时才运行 `schema apply`。

### 终端中文乱码

使用框架生成的 `lark-ledger.ps1` 启动器；它会强制 Python 使用 UTF-8。

### 企业代理/网络错误

确认电脑可访问：

```text
https://open.larksuite.com
https://<公司租户>.larksuite.com
```

如果公司要求代理或域名白名单，请联系 IT，不要关闭终端安全软件绕过。

## 13. 安全要求

严禁：

- 把 App Secret 发到聊天、邮件正文、工单截图或代码仓库；
- 把 `identity.env`、token SQLite、WAL/SHM 文件放入项目；
- 在不同电脑间复制当前用户 token 数据库；
- 让 Codex、脚本或同事代填个人 Lark 密码/MFA；
- 多人共用个人账号却没有集中审计。

建议：

- App Secret 由公司密码管理工具或终端管理系统分发；
- 每位测试人员使用自己的公司账号 OAuth；
- 定期检查 App scope 和目标 Base 成员；
- 人员离职或权限变化时，从 App 可用范围和 Base 成员中移除，并撤销 OAuth；
- 丢失电脑时立即轮换 App Secret并撤销相关用户授权。

## 14. 卸载或切换项目

删除某项目的本地集成，只需移除该项目的：

```text
.lark-test-ledger/
```

这不会删除 Lark Base，也不会删除其他项目共享的身份配置。

如果要彻底移除本机身份，在确认没有其他项目使用后，删除：

```text
%LOCALAPPDATA%\LarkTestLedger
```

然后在 Lark 的应用授权管理中撤销该 App 的用户授权。

## 15. 配置流程还能如何继续简化

当前 `0.3.0` 已把普通同事操作压缩为一条向导命令，人工只剩：

1. 首次安全取得/输入 App Secret；
2. 在 Lark 官方页面登录、MFA、确认授权；
3. 从项目负责人取得 Base URL；
4. 由负责人授予 Base 权限。

下一阶段最值得做的是部署公司内部“Lark 测试账本连接服务”：

- App Secret 只保存在服务器；
- 浏览器仍由用户本人 OAuth；
- 项目只配置 Base URL；
- Codex 通过内部 API/MCP 读写测试账本；
- 服务统一处理 token 刷新、权限、审计、速率限制和撤销。

这样其他测试人员电脑上不再需要 App Secret 或 token SQLite，是多人规模化时最简单、
最安全的最终形态。
