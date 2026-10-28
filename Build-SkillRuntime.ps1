#Requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot 'skill\lark-test-ledger\scripts\lark-test-ledger.pyz'
$builder = @'
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
source = Path(sys.argv[1])
with ZipFile(sys.argv[2], 'w', compression=ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob('*.py')):
        if '__pycache__' not in path.parts:
            archive.write(path, path.relative_to(source).as_posix())
    archive.writestr('__main__.py', 'from dms_test_ledger.cli import main\nraise SystemExit(main())\n')
'@
& python -c $builder (Join-Path $PSScriptRoot 'src') $runtime
if ($LASTEXITCODE -ne 0) { throw 'Skill 运行时打包失败。请检查 Python 和源码目录。' }
