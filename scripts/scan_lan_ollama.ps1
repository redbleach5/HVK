# From the NVIDIA PC: find another Ollama on the LAN (port 11434).
# Windows PowerShell 5 compatible.
$ErrorActionPreference = "SilentlyContinue"
$my = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*"
})
if (-not $my) { Write-Host "no private IPv4"; exit 1 }
$prefix = $my[0].IPAddress
$parts = $prefix.Split(".")
$base = "$($parts[0]).$($parts[1]).$($parts[2])"
Write-Host "scan ${base}.0/24 :11434 (this host $prefix)"
$hits = @()
for ($i = 1; $i -le 254; $i++) {
    $ip = "$base.$i"
    try {
        $r = Invoke-WebRequest -Uri "http://${ip}:11434/api/version" -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -eq 200) {
            $hits += $ip
            Write-Host "OLLAMA $ip"
        }
    } catch {}
}
if ($hits.Count -eq 0) { Write-Host "no ollama on LAN" }
