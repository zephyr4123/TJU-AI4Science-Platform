# AAAI4S 一行命令安装（Windows）：外层 #277 留的槽位，外层 #210 Windows 适配时填上。
#
#     irm https://media.zephyrxiang.com/ai4science/dist/install.ps1 | iex
#
# 与 install.sh 同样只做两件事：装 uv、装平台，然后交给 `ai4sci setup`（查 git、装两家 CLI、问 key、
# 起服务）。Windows 上平台还跑不通（进程、编码、路径见外层 docs/specs/windows-adaptation.md），所以
# 现在明确说还没做，不装半份。
Write-Host "AAAI4S 的 Windows 安装还没做：https://github.com/zephyr4123/TJU-AI4Science/issues/210"
exit 1
