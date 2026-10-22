# Xuất ảnh bán hàng 1920x1080 cho từng mã màn từ mau-ban-hang.html
# Chạy: powershell -ExecutionPolicy Bypass -File xuat-anh.ps1
$root = $PSScriptRoot
$out = Join-Path $root "Anh-ban-hang"
New-Item -ItemType Directory -Force $out | Out-Null
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$tpl = ([System.Uri](Join-Path $root "mau-ban-hang.html")).AbsoluteUri
$models = [ordered]@{
  "g274qpx"    = "MSI-G274QPX"
  "g274qpf-e2" = "MSI-G274QPF-E2"
  "g274qrfw"   = "MSI-G274QRFW"
  "g272qpf-e2" = "MSI-G272QPF-E2"
  "mp273qp"    = "MSI-PRO-MP273QP"
}
foreach ($k in $models.Keys) {
  $png = Join-Path $out ("{0}-ASL-Workshop.png" -f $models[$k])
  & $chrome --headless=new --disable-gpu --hide-scrollbars --window-size=1920,1080 --virtual-time-budget=8000 "--screenshot=$png" "$tpl`?m=$k" 2>$null | Out-Null
  Write-Output $png
}
