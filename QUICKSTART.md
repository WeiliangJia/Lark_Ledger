# 快速开始

本页面向第一次使用Lark Test Ledger的测试人员。完整管理员配置、安全和排错说明见
[COMPANY_SETUP_GUIDE.md](COMPANY_SETUP_GUIDE.md)。

## 1. 准备环境

需要：

- Windows 10/11；
- PowerShell 7；
- Python 3.11+；
- 公司Lark账号；
- Lark自建App的App ID/App Secret；
- 包含`table=...`的目标Base/Wiki完整URL；
- 对目标Base的编辑权限。

检查：

```powershell
pwsh --version
python --version
```

## 2. 安装Skill

在仓库根目录运行：

```powershell
& '.\Install-LarkTestLedgerSkill.ps1'
```

安装后重新启动Codex。Skill根目录通常为：

```text
C:\Users\<本人>\.codex\skills\lark-test-ledger
```

## 3. 首次配置本机身份

每个Windows用户只运行一次：

```powershell
$skillRoot = 'C:\Users\<本人>\.codex\skills\lark-test-ledger'

& "$skillRoot\scripts\Setup-LarkTestLedgerIdentity.ps1"
```

脚本会在终端隐藏读取App Secret，并打开Lark OAuth页面。登录密码、MFA和授权确认只在
Lark官方页面完成。

默认身份配置位置：

```text
%LOCALAPPDATA%\LarkTestLedger\identity.env
```

身份指针：

```text
%LOCALAPPDATA%\LarkTestLedger\skill.env
```

## 4. 配置项目

进入目标项目，运行：

```powershell
$skillRoot = 'C:\Users\<本人>\.codex\skills\lark-test-ledger'

& "$skillRoot\scripts\Setup-LarkTestLedgerProject.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  -BaseUrl 'https://company.sg.larksuite.com/wiki/xxx?table=tblxxx&view=vewxxx' `
  -TableName '测试用例'
```

脚本会创建：

```text
<project>\.lark-test-ledger\ledger.env
```

该目录应被Git忽略。项目配置只引用本机身份文件，不复制App Secret或token。

## 5. 检查连接

```powershell
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' doctor
```

期望`authorized`、`target_accessible`、`schema_ready`和`ready`为`true`。

如果Schema不完整，先查看计划：

```powershell
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' schema plan
```

只有确认目标是测试账本后才执行`schema apply`。

## 6. 生成与同步

```powershell
# 校验Manifest和来源
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  validate '.\cases\manifest.json' --verify-sources

# 同步预览，不写入
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  sync '.\cases\manifest.json'

# 人工确认差异后提交
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  sync '.\cases\manifest.json' --commit
```

## 7. 执行用例

```powershell
# 提测集
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  case list --submission-only

# 下一条未执行提测用例
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' execution next

# 通过
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  execution record --case-id 'PROJECTA-TC-001' `
  --result passed --notes '符合预期'

# 失败并追加证据
& "$skillRoot\scripts\Invoke-LarkTestLedger.ps1" `
  -ProjectRoot 'D:\Projects\ProjectA' `
  execution record --case-id 'PROJECTA-TC-002' `
  --result failed --notes '保存时报错' `
  --evidence '.\evidence\PROJECTA-TC-002.png'
```

## 8. 环境文件

仓库里的`identity.env.example`、`project.env.example`以及Skill资产中的示例文件所有值均
故意留空。复制到私有位置后再填写。

禁止提交：

- `identity.env`、`ledger.env`；
- App Secret；
- OAuth token、SQLite、WAL、SHM；
- 真实证据、Manifest归档或执行缓存。

## 9. 卸载

```powershell
& '.\Uninstall-LarkTestLedgerSkill.ps1'
```

卸载Skill不会删除Lark Base。删除本机身份前，应确认没有其他项目继续使用它，并在Lark
授权管理中撤销授权。
