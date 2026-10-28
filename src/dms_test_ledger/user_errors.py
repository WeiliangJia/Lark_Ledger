"""Actionable messages without echoing credentials or remote response bodies."""
from .errors import AuthenticationError, ConfigError, LarkApiError, ManifestError, SchemaError


def explain_error(error: Exception) -> str:
    if isinstance(error, AuthenticationError):
        return 'Lark 授权不可用或已过期。请运行 auth，在浏览器完成登录和授权；确认回调地址为 http://127.0.0.1:8765/callback。'
    if isinstance(error, ConfigError):
        return '配置文件缺失或格式错误。请重新运行 Start-LarkTestLedger.ps1，或检查 --env-file 指向的文件、身份文件引用、App 配置和 Base URL（需包含 table=...）。不要将凭据粘贴到聊天中。'
    if isinstance(error, LarkApiError):
        reference = f'（HTTP {error.status}，Lark code {error.code}）'
        if error.status == 401:
            return f'Lark 拒绝了当前授权{reference}。请运行 auth 重新授权。'
        if error.status in (403, 404):
            return f'目标不可访问{reference}。请检查 Base URL、当前账号的 Wiki/Base 编辑权限，以及自建应用的权限和发布范围。'
        if error.status == 429:
            return f'Lark 请求过于频繁{reference}。工具重试后仍失败，请稍后重试。'
        if (error.status is None and 'network' in str(error).lower()) or (error.status is not None and error.status >= 500):
            return f'Lark 网络连接或服务异常{reference}。请检查网络、公司代理及 open.larksuite.com 的访问情况，稍后重试。'
        return f'Lark API 拒绝请求{reference}。请检查应用权限是否已发布、账号的 Base 权限和字段类型；运行 doctor 检查连接。'
    if isinstance(error, ManifestError):
        return f'用例文件校验失败：{error}。请修正 Manifest；需求源文件变化时，重新核实需求并生成来源哈希，再运行 validate --verify-sources。'
    if isinstance(error, SchemaError):
        return '账本字段缺失或类型不匹配。请运行 schema plan 查看差异，并核实目标表；不要直接覆盖已有字段。'
    if isinstance(error, PermissionError):
        return '本地文件没有读写权限。请检查配置、状态库和附件目录的访问权限，以及文件是否被其他程序占用。'
    if isinstance(error, FileNotFoundError):
        return '本地文件不存在。请检查配置、Manifest、需求来源和附件路径，确认文件已经保存。'
    if isinstance(error, OSError):
        return '本地文件或系统操作失败。请检查目录权限、磁盘空间和文件是否被占用，再重试。'
    return f'输入或操作无效：{error}。请检查命令参数，使用 --help 查看示例。'
