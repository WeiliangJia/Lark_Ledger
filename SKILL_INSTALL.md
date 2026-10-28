# 安装用户级 Codex Skill

首次使用推荐运行 `./Start-LarkTestLedger.ps1`，统一完成环境检查、客户端选择、安装和授权。
手工安装可指定 `-Client Codex`（默认）、`-Client ClaudeCode` 或 `-Client Qoder`。
后两者分别安装到 `%USERPROFILE%\.claude\skills` 和 `%USERPROFILE%\.qoder\skills`，不创建 Codex 兼容链接。
Qoder 图形界面也可导入整个 `skill/lark-test-ledger` 文件夹。尚未完成其他客户端端到端验证。
卸载时传入相同的 `-Client`；建议加 `-KeepIdentity`，保留其他项目共享的身份配置。

修改 Python 源码后运行 `./Build-SkillRuntime.ps1`，更新 Skill 内的运行时。

使用 PowerShell 7，在仓库根目录运行：

```powershell
& '.\Install-LarkTestLedgerSkill.ps1'
```

安装脚本默认从`skill/lark-test-ledger`复制Skill。目标位置为：

```text
%CODEX_HOME%\skills\lark-test-ledger
```

若未设置`CODEX_HOME`，使用：

```text
%USERPROFILE%\.codex\skills\lark-test-ledger
```

脚本还会创建官方兼容发现Junction：

```text
%USERPROFILE%\.agents\skills\lark-test-ledger
```

安装后请新建Codex任务或重启应用：

- ChatGPT桌面端：`@Lark 测试账本`
- Codex CLI/IDE：`$lark-test-ledger`

如果同一台受控电脑已经有身份配置，可以显式引用私有身份文件：

```powershell
& '.\Install-LarkTestLedgerSkill.ps1' `
  -IdentityEnv 'C:\Secure\LarkTestLedger\identity.env'
```

不要把填有真实值的身份文件、App Secret或OAuth token放入本仓库。
