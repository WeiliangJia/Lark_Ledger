# Changelog

## Unreleased

- 新增 `Start-LarkTestLedger.ps1`，统一环境检查、客户端选择、Skill 安装、身份配置、OAuth 和只读 Base 检查。
- 支持安装到 Codex、Claude Code、Qoder 的标准 Skill 目录；后两者尚未完成客户端端到端验证。
- 重复初始化保留已有 Skill 和目标 Base；项目配置脚本拒绝隐式覆盖。
- 增加中文错误说明及下一步修复建议；`doctor` 字段不就绪时返回失败退出码。
- 增加 MIT License、源码与打包运行时同步脚本，以及隔离安装测试。

## Skill 0.4.0 / Framework 0.3.0

- 发布用户级`lark-test-ledger` Codex Skill；
- 增加共享身份与项目配置两层模型；
- 提供身份和项目配置向导；
- 提供Manifest验证、同步dry-run/commit、用例执行和证据追加；
- 提供完整Python源码、单元测试和JSON Schema；
- 示例`.env`改为仅保留键名、所有值为空；
- 增加公开仓库README、快速开始和安全说明。
