#Requires -Version 5.1
<#
.SYNOPSIS
    Runs both test suites and updates the test counts recorded in the docs.

.DESCRIPTION
    Three docs each state the current test counts in their own words
    (docs/PROJECT_STATUS.md, docs/AI_START_HERE.md, docs/AI_HANDOFF.md), and
    CLAUDE.md's "Before ending a session" asks that they still describe
    reality. Getting the number by hand and editing three files with `sed`
    is exactly the kind of step that quietly goes stale or gets a typo.

    This runs `pytest` and the frontend `vitest` suite, reads the counts back
    out of their own output, and replaces just the numbers - "NNN backend"
    and "NNN frontend" - leaving everything else in each sentence as its
    author wrote it. Prints a diff-style summary; nothing is committed.

    Only the line that carries the marker `<!-- sync-tests -->` is rewritten,
    one in each doc. Those docs also quote other, unrelated counts ("161
    backend and 61 frontend tests" of one feature, say), and rewriting every
    "NNN backend" in the file would have overwritten them with the suite's
    total. A doc with no marked line, or a marked line without both numbers,
    is an error: the count would otherwise go stale without a word.

.EXAMPLE
    .\scripts\sync-test-counts.ps1
#>

$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot ".."

# Both tools colour their output when they think they're on a terminal, and
# get it wrong when this script itself is run non-interactively (an MCP tool
# call, CI, another script's captured output rather than a real console):
# the count is then surrounded by ANSI escape codes instead of plain spaces,
# and a regex expecting whitespace stops matching. NO_COLOR/FORCE_COLOR are
# the standard opt-out most CLI tools (npm, vitest's chalk) respect; the
# strip below is the fallback for whichever one does not.
$env:NO_COLOR = "1"
$env:FORCE_COLOR = "0"
$ansiPattern = "$([char]27)\[[0-9;]*[a-zA-Z]"
function ConvertTo-PlainText([string]$text) {
    return $text -replace $ansiPattern, ""
}

Write-Host "Running backend tests ..." -ForegroundColor Cyan
Push-Location (Join-Path $root "backend")
try {
    # no 2>&1 here: PowerShell 5.1 wraps a native command's stderr lines in a
    # NativeCommandError and, with $ErrorActionPreference = Stop, that aborts
    # this script even on a passing run (e.g. npm's own update notice) -
    # stdout/stderr are both already visible without redirecting either
    $backendOutput = ConvertTo-PlainText (& ".\.venv\Scripts\python.exe" -m pytest -q | Out-String)
}
finally {
    Pop-Location
}
Write-Host $backendOutput
if ($backendOutput -notmatch "(\d+) passed") {
    Write-Host "[ERROR] Could not find a passing count in the backend output; nothing was changed." -ForegroundColor Red
    exit 1
}
$backendCount = $Matches[1]

Write-Host "Running frontend tests ..." -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
try {
    $frontendOutput = ConvertTo-PlainText (& npm.cmd run test | Out-String)
}
finally {
    Pop-Location
}
Write-Host $frontendOutput
if ($frontendOutput -notmatch "Tests\s+(\d+) passed") {
    Write-Host "[ERROR] Could not find a passing count in the frontend output; nothing was changed." -ForegroundColor Red
    exit 1
}
$frontendCount = $Matches[1]

Write-Host "Backend: $backendCount passed. Frontend: $frontendCount passed." -ForegroundColor Green

$docs = @(
    (Join-Path $root "docs\PROJECT_STATUS.md"),
    (Join-Path $root "docs\AI_START_HERE.md"),
    (Join-Path $root "docs\AI_HANDOFF.md")
)
$marker = "<!-- sync-tests -->"
$failed = $false

foreach ($doc in $docs) {
    if (!(Test-Path $doc)) {
        Write-Host "  [WARN] $doc not found, skipped." -ForegroundColor Yellow
        continue
    }
    # Read/written as raw UTF-8 without a BOM via .NET, not Get-/Set-Content:
    # these docs hold Polish text with no BOM, and PowerShell 5.1's own
    # encoding defaults (ASCII on write, guesswork on read) would corrupt or
    # silently re-encode it - the same class of bug CLAUDE.md warns about
    # for piped stdin, just on the write side instead.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $before = [System.IO.File]::ReadAllText($doc, $utf8NoBom)

    # line by line, each line keeping its own terminator (the docs are CRLF),
    # and only a marked line is touched
    $marked = 0
    $docFailed = $false
    $rewritten = foreach ($line in [regex]::Split($before, '(?<=\n)')) {
        if ($line.Contains($marker)) {
            $marked++
            $line = $line -replace '\d+(?= backend)', $backendCount `
                          -replace '\d+(?= frontend)', $frontendCount
            if ($line -notmatch '\d+ backend' -or $line -notmatch '\d+ frontend') {
                Write-Host "  [ERROR] The line marked $marker in $doc has no 'NNN backend' and 'NNN frontend' to update." -ForegroundColor Red
                $docFailed = $true
            }
        }
        $line
    }
    if ($marked -eq 0) {
        Write-Host "  [ERROR] No line in $doc carries $marker, so its test counts were not updated." -ForegroundColor Red
        $docFailed = $true
    }
    if ($docFailed) {
        # a doc that could not be updated whole is left as it was
        $failed = $true
        continue
    }
    $after = -join $rewritten
    if ($after -ne $before) {
        [System.IO.File]::WriteAllText($doc, $after, $utf8NoBom)
        Write-Host "  updated $doc"
    }
    else {
        Write-Host "  $doc already says $backendCount / $frontendCount"
    }
}

Write-Host ""
if ($failed) {
    Write-Host "[ERROR] Some test counts were not updated (see above)." -ForegroundColor Red
    exit 1
}
Write-Host "Review the changes (git diff), then commit them with the rest of the work." -ForegroundColor Cyan
