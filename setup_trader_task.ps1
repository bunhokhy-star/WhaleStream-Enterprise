# ============================================================
# WHALE-STREAM TRADER — Task Scheduler Setup
# Run this ONCE as Administrator to schedule the trader.
#
# Schedule: Every 2 hours at :20 (12 min after bot runs at :08)
# This gives the bot time to write signals to Google Sheets.
# ============================================================

$TaskName   = "WhaleStream-Trader"
$BatFile    = "C:\Users\MAX\WhaleStream\run_trader.bat"
$StartTime  = "06:20"   # First run at 06:20 BKK today

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "   Removed existing $TaskName task"
}

# Build trigger: every 2 hours starting at 06:20
$trigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -Once `
    -At $StartTime

# Action: run the bat file
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatFile`""

# Settings: allow running on battery, start if missed
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName   $TaskName `
    -Trigger    $trigger `
    -Action     $action `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force

Write-Host ""
Write-Host "==================================================="
Write-Host "  WhaleStream-Trader scheduled successfully!"
Write-Host "  Runs every 2 hours at :20 past the hour"
Write-Host "  (12 minutes after bot generates signals at :08)"
Write-Host ""
Write-Host "  To run NOW immediately:"
Write-Host "  Start-ScheduledTask -TaskName 'WhaleStream-Trader'"
Write-Host "==================================================="
