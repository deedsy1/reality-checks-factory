\
param(
  [Parameter(Mandatory=$true)][string]$SiteTitle,
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$false)][string]$Brand = "",
  [Parameter(Mandatory=$false)][switch]$WipePages
)

# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/new_site_bootstrap.ps1 -SiteTitle "My New Site" -BaseUrl "https://my-new-site.pages.dev/" -Brand "My New Site" -WipePages

if ($Brand -eq "") { $Brand = $SiteTitle }

Write-Host "== Bootstrapping site ==" -ForegroundColor Cyan
Write-Host "Title: $SiteTitle"
Write-Host "Brand: $Brand"
Write-Host "BaseUrl: $BaseUrl"
Write-Host ""

# 1) Update hugo.yaml (simple line replacements)
$hugoPath = "hugo.yaml"
if (Test-Path $hugoPath) {
  $hugo = Get-Content $hugoPath -Raw

  $hugo = $hugo -replace '(^title:\s*").*?(")', ('title: "' + $SiteTitle + '"')
  $hugo = $hugo -replace '(^baseURL:\s*").*?(")', ('baseURL: "' + $BaseUrl + '"')

  Set-Content -Path $hugoPath -Value $hugo -Encoding UTF8
  Write-Host "Updated hugo.yaml" -ForegroundColor Green
} else {
  Write-Host "WARN: hugo.yaml not found" -ForegroundColor Yellow
}

# 2) Update scripts/site_config.yaml
$configPath = "scripts/site_config.yaml"
if (Test-Path $configPath) {
  $cfg = Get-Content $configPath -Raw

  $cfg = $cfg -replace '(?m)^\s*title:\s*".*"$', ('  title: "' + $SiteTitle + '"')
  $cfg = $cfg -replace '(?m)^\s*brand:\s*".*"$', ('  brand: "' + $Brand + '"')
  $cfg = $cfg -replace '(?m)^\s*base_url:\s*".*"$', ('  base_url: "' + $BaseUrl + '"')

  Set-Content -Path $configPath -Value $cfg -Encoding UTF8
  Write-Host "Updated scripts/site_config.yaml" -ForegroundColor Green
} else {
  Write-Host "WARN: scripts/site_config.yaml not found" -ForegroundColor Yellow
}

# 3) Reset manifest
$manifestPath = "scripts/manifest.json"
$manifest = @{ used_titles = @(); generated_this_run = @() } | ConvertTo-Json -Depth 4
Set-Content -Path $manifestPath -Value $manifest -Encoding UTF8
Write-Host "Reset scripts/manifest.json" -ForegroundColor Green

# 4) Optionally wipe pages
if ($WipePages) {
  $pagesDir = "content/pages"
  if (Test-Path $pagesDir) {
    Get-ChildItem $pagesDir -Directory | Remove-Item -Recurse -Force
    Write-Host "Wiped content/pages/*" -ForegroundColor Green
  } else {
    Write-Host "WARN: content/pages not found" -ForegroundColor Yellow
  }
}

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Cyan
Write-Host "1) Replace scripts/titles_pool.txt with your new niche titles"
Write-Host "2) Commit + push"
Write-Host "3) Create a new Cloudflare Pages project pointing to the repo"
