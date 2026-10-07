# AAAI4S 一行命令安装（Windows，外层 #210）：在 PowerShell 里
#
#     irm https://media.zephyrxiang.com/ai4science/dist/install.ps1 | iex
#
# 与 install.sh 是同一件事：只做 Python 还没有时非做不可的事——装 uv、装平台，然后交给
# `ai4sci setup`（查 git、装两家 CLI、问 key、起服务）。全程国内源；每一项先查，装过的跳过；重跑
# 就是升级。装出来的都在平台的家里（~\.ai4sci），落在外面的只有用户 Path 里一项。
#
# 下面的地址与目录名和 framework/mirrors.py、framework/paths.py 是同一份事实，
# tests/test_install_script.py 对账。__VERSION__ 这类占位由发版流水线写进去（.github/scripts/cdn.py）。
#
# `irm | iex` 是在人自己的会话里跑的：整段包在一个脚本块里（变量、$ErrorActionPreference 不漏到他的
# 会话），出错只说一句、不 exit（exit 会关掉他的窗口）；不靠执行策略（iex 跑的是字符串，不是 .ps1）。

& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # 5.1 的下载进度条让 Invoke-WebRequest 慢几十倍
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$VERSION = '__VERSION__'
$UV_VERSION = '__UV_VERSION__'
$DIST = if ($env:AI4SCI_DIST) { $env:AI4SCI_DIST } else { 'https://media.zephyrxiang.com/ai4science/dist' }
$PYPI_INDEX = 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple'
$PYTHON_DOWNLOADS = 'https://registry.npmmirror.com/-/binary/python-build-standalone'
$PYTHON_WANTED = '>=3.12'
$PYTHON_INSTALL = '3.12'
$HOME_DIR = if ($env:AI4SCI_HOME) { $env:AI4SCI_HOME } else { Join-Path $HOME '.ai4sci' }
$BIN = Join-Path $HOME_DIR 'bin'
$TOOLS = Join-Path $HOME_DIR 'tools'
$LOG = Join-Path $HOME_DIR 'install.log'
$UTF8 = New-Object Text.UTF8Encoding $false
$STOP = 'ai4sci-install-stop'  # 已经说过为什么的停：外面只补一句怎么办

function Say([string]$mark, [string]$label, [string]$note) {
  Write-Host ('  {0} {1,-14}{2}' -f $mark, $label, $note)
}
function Stop-Install([string]$label, [string]$note) {
  Say '✗' $label $note
  throw $STOP
}

# 下载 $url 到 $dest 并和旁边的 .sha256 对账：对不上就停，不装半份
function Fetch([string]$url, [string]$dest, [string]$label) {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest
    Invoke-WebRequest -UseBasicParsing -Uri "$url.sha256" -OutFile "$dest.sha256"
  } catch {
    Stop-Install $label "取不到 ${url}：$($_.Exception.Message)"
  }
  $want = ([IO.File]::ReadAllText("$dest.sha256")).Trim().Split()[0]
  # 用 .NET 算，不用 Get-FileHash：5.1 里它是模块的脚本函数，从 pwsh 里开的 5.1 加载不到
  $sha = [Security.Cryptography.SHA256]::Create()
  $stream = [IO.File]::OpenRead($dest)
  try { $got = -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) }
  finally { $stream.Dispose(); $sha.Dispose() }
  if ($got -ne $want) { Stop-Install $label "$url 的 sha256 对不上，没装" }
}

# 跑一条命令，输出记进日志，返回退出码。原生命令写 stderr 在 'Stop' 下会被当成异常，这里放宽
function Invoke-Logged([string]$exe, [string[]]$argv, [hashtable]$envs = @{}) {
  $saved = @{}
  foreach ($k in $envs.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envs[$k]) }
  $ErrorActionPreference = 'Continue'
  try {
    $out = & $exe @argv 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
  } finally {
    foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
  }
  [IO.File]::AppendAllText($LOG, (($out -join "`r`n") + "`r`n"), $UTF8)
  return $code
}

# uv 的环境：Python、平台本体、缓存都在家里，下载走国内源；装 Python 不往 ~\.local\bin 放入口、
# 不登记进注册表（登记了，删掉家以后注册表里还指着它，别的 uv 还会找到它，外层 #210 真机撞上）
$UV_HOME = @{
  UV_PYTHON_INSTALL_DIR = (Join-Path $TOOLS 'python'); UV_PYTHON_INSTALL_MIRROR = $PYTHON_DOWNLOADS
  UV_PYTHON_INSTALL_BIN = '0'; UV_PYTHON_INSTALL_REGISTRY = '0'; UV_DEFAULT_INDEX = $PYPI_INDEX
  UV_CACHE_DIR = (Join-Path $HOME_DIR 'cache\uv')
  UV_TOOL_DIR = (Join-Path $TOOLS 'ai4sci'); UV_TOOL_BIN_DIR = $BIN
}
# 找以前装在 uv 缺省位置的那份：工具目录用缺省的，缓存仍在家里
$UV_DEFAULT = @{ UV_CACHE_DIR = (Join-Path $HOME_DIR 'cache\uv') }

try {
  Write-Host 'AAAI4S 安装（全程国内源）'
  # 家的标记（同 framework/paths.py 的 mark）：新家、空家才放；指到一个已有东西的目录不放，清除就不认它
  if (-not (Test-Path $HOME_DIR) -or -not (Get-ChildItem -Force $HOME_DIR | Select-Object -First 1)) {
    New-Item -ItemType Directory -Force $HOME_DIR | Out-Null
    [IO.File]::WriteAllText((Join-Path $HOME_DIR '.ai4sci-home'),
      "ai4sci 的家（外层 #263）：清除只删有这个文件的目录。`n", $UTF8)
  }
  New-Item -ItemType Directory -Force $BIN, $TOOLS | Out-Null
  $work = Join-Path ([IO.Path]::GetTempPath()) ("ai4sci-" + [Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory $work | Out-Null

  try {
    # 1. uv：用户有就用他的；家里装过就用家里的；都没有从我们的 CDN 取
    $mine = Join-Path $TOOLS 'uv\uv.exe'
    if ($found = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1) {
      $UV = $found.Source
      Say '✓' 'uv' '已装，跳过'
    } elseif (Test-Path $mine) {
      $UV = $mine
      Say '✓' 'uv' '已装，跳过'
    } else {
      $arch = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture
      $triple = switch ($arch) {
        'X64' { 'x86_64-pc-windows-msvc' }
        'Arm64' { 'aarch64-pc-windows-msvc' }
        default { Stop-Install 'uv' "Windows $arch 没有现成的安装包" }
      }
      Fetch "$DIST/uv/$UV_VERSION/uv-$triple.zip" (Join-Path $work 'uv.zip') 'uv'
      # 不用 Expand-Archive：模块里的函数不认这里的 $ProgressPreference，会画一大片进度条
      Add-Type -AssemblyName System.IO.Compression.FileSystem
      [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $work 'uv.zip'), (Join-Path $work 'uv'))
      New-Item -ItemType Directory -Force (Join-Path $TOOLS 'uv') | Out-Null
      Copy-Item (Join-Path $work 'uv\*.exe') (Join-Path $TOOLS 'uv')
      $UV = $mine
      Say '✓' 'uv' "$UV_VERSION，下载完成"
    }

    # 2. Python：有够版本的就用，没有装进家里（微软商店那个占位的 python.exe uv 不认）
    $ErrorActionPreference = 'Continue'
    $saved = @{}
    foreach ($k in $UV_HOME.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $UV_HOME[$k]) }
    try { $py = & $UV python find $PYTHON_WANTED 2>$null; $pyCode = $LASTEXITCODE }
    finally { foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) } }
    $ErrorActionPreference = 'Stop'
    if ($pyCode -eq 0 -and $py) {
      Say '✓' 'Python' "$(& $py -c 'import platform; print(platform.python_version())')，已装，跳过"
    } else {
      if ((Invoke-Logged $UV @('python', 'install', $PYTHON_INSTALL) $UV_HOME) -ne 0) {
        Stop-Install 'Python' "装不上，详情在 $LOG"
      }
      Say '✓' 'Python' "$PYTHON_INSTALL，下载完成"
    }

    # 3. 平台：已是这一版就跳过；以前用 uv 装在缺省位置的先卸掉，不然终端里有两份 ai4sci（外层 #274）
    $ErrorActionPreference = 'Continue'
    $saved = $env:UV_CACHE_DIR; $env:UV_CACHE_DIR = $UV_DEFAULT.UV_CACHE_DIR
    try { $listed = & $UV tool list 2>$null } finally { $env:UV_CACHE_DIR = $saved }
    $ErrorActionPreference = 'Stop'
    if ($listed | Where-Object { $_ -match '^ai4sci ' }) {
      if ((Invoke-Logged $UV @('tool', 'uninstall', 'ai4sci') $UV_DEFAULT) -ne 0) {
        Stop-Install 'ai4sci' "卸不掉以前的那份，详情在 $LOG"
      }
      Say '✓' 'ai4sci' '卸掉了以前 uv 装在缺省位置的那份，换成家里这份'
    }
    $exe = Join-Path $BIN 'ai4sci.exe'
    $old = Get-Command ai4sci -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($old -and $old.Source -ne $exe) {
      Say '!' 'ai4sci' "$($old.Source) 不是 uv 装的，没动；终端里先找到的可能是它"
    }
    # 装坏了的那份往 stderr 写 traceback，Stop 下 5.1 会当异常抛：坏了就当没装，照装
    $ErrorActionPreference = 'Continue'
    $have = if (Test-Path $exe) { & $exe --version 2>$null } else { '' }
    $ErrorActionPreference = 'Stop'
    if ($have -eq "ai4sci $VERSION") {
      Say '✓' 'ai4sci' "$VERSION，已装，跳过"
    } else {
      # 在跑的程序换不掉：服务或作业开着时，uv 删到 Scripts\ 才被拒，删掉的已经回不来
      $tool = Join-Path $TOOLS 'ai4sci'
      $busy = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and ($_.Path -eq $exe -or $_.Path.StartsWith("$tool\", [StringComparison]::OrdinalIgnoreCase))
      })
      if ($busy) {
        Stop-Install 'ai4sci' "平台还开着（$($busy.Count) 个进程在用它）：关掉服务的窗口，作业在跑就等它跑完或在页面上停掉"
      }
      $wheel = "ai4sci-$VERSION-py3-none-any.whl"
      Fetch "$DIST/$VERSION/$wheel" (Join-Path $work $wheel) 'ai4sci'
      $argv = @('tool', 'install', '--force', '--python', $PYTHON_WANTED, (Join-Path $work $wheel))
      if ((Invoke-Logged $UV $argv $UV_HOME) -ne 0) { Stop-Install 'ai4sci' "装不上，详情在 $LOG" }
      Say '✓' 'ai4sci' "$VERSION，安装完成"
    }
  } finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
  }

  # 4. Path：用户的 Path 里加上 bin\，新开的终端里敲得到 ai4sci；有了不重复加。按原样读写
  #    （REG_EXPAND_SZ、不展开 %变量%），不然别的项里的 %USERPROFILE% 会被写死
  $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
  try {
    $raw = [string]$key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    $items = @($raw -split ';' | Where-Object { $_ })
    if ($items -contains $BIN) {
      Say '✓' 'Path' '用户的 Path 里已经有了'
    } else {
      $key.SetValue('Path', ((@($BIN) + $items) -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
      # 写注册表不会通知已开着的程序；借设一个变量让系统广播一次「环境变了」，新开的终端才认
      [Environment]::SetEnvironmentVariable('AI4SCI_INSTALLING', '1', 'User')
      [Environment]::SetEnvironmentVariable('AI4SCI_INSTALLING', $null, 'User')
      Say '✓' 'Path' '写进了用户的 Path，新开的终端里敲 ai4sci 就能用'
    }
  } finally {
    $key.Close()
  }
  # 这个窗口里也马上能用
  if (($env:Path -split ';') -notcontains $BIN) { $env:Path = "$BIN;$env:Path" }

  # 5. 剩下的交给平台自己。装到这里已经成了，setup 成没成它自己说；它起的服务往 stderr 写日志，
  #    stderr 被并进来的宿主（ISE、`| Tee-Object`）里 5.1 在 Stop 下会把第一行日志当异常、掐断服务
  $ErrorActionPreference = 'Continue'
  & (Join-Path $BIN 'ai4sci.exe') setup
} catch {
  if ("$_" -ne $STOP) { Say '✗' 'ai4sci' "$_" }
  Write-Host '没装完：照上面那句处理后，再跑一次同一行命令。'
}
}
