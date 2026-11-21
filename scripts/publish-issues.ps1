# Publishes .github/issues/*.md as GitHub Issues. Requires the GitHub CLI and `gh auth login`.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/publish-issues.ps1
$repo = "Eterphis/hacknation-2026-innovation-radar"
Get-ChildItem .github/issues/*.md | Sort-Object Name | ForEach-Object {
  $raw = Get-Content $_.FullName -Raw -Encoding UTF8
  $m = [regex]::Match($raw, '(?s)^---\s*(.*?)\s*---\s*(.*)$')
  $front = $m.Groups[1].Value
  $body = $m.Groups[2].Value
  $title = [regex]::Match($front, 'title:\s*"(.*)"').Groups[1].Value
  $labels = ([regex]::Match($front, 'labels:\s*\[(.*)\]').Groups[1].Value -split ',\s*') | Where-Object { $_ }
  foreach ($l in $labels) { gh label create $l --repo $repo --force | Out-Null }
  $tmp = New-TemporaryFile
  Set-Content -Path $tmp -Value $body -Encoding UTF8
  gh issue create --repo $repo --title $title --body-file $tmp --label ($labels -join ',')
  Remove-Item $tmp
}
