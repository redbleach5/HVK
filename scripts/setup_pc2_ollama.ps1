# Run ON the RX 7700 XT PC (Windows, same LAN).
# Install Ollama from https://ollama.com first, then:
#   powershell -ExecutionPolicy Bypass -File setup_pc2_ollama.ps1

$ErrorActionPreference = "Stop"
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "32768", "User")
$env:OLLAMA_HOST = "0.0.0.0:11434"

Write-Host "User env set. Restart the Ollama app from the tray if it is already running."

$rule = "Ollama LAN 11434"
if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow -Profile Private | Out-Null
    Write-Host "Firewall: inbound 11434 on Private."
}

ollama pull gemma4:12b
Write-Host "--- this PC IPv4 (put into HVK .env as EYES_BASE_URL) ---"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -ne "WellKnown" -and $_.IPAddress -notlike "127.*" } | ForEach-Object { $_.IPAddress }

Write-Host "Test from the NVIDIA PC:"
Write-Host "  curl http://<this-ip>:11434/api/tags"
