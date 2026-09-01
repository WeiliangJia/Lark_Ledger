# 安装用户级 Codex Skill

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
