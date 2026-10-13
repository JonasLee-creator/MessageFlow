$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $env:DASHSCOPE_API_KEY -or $env:DASHSCOPE_API_KEY.Length -lt 8) {
    throw "DASHSCOPE_API_KEY is missing in this window. Use the window where the key was entered."
}
if (-not $env:BAILIAN_CHAT_URL) { throw "BAILIAN_CHAT_URL is missing in this window." }
if (-not $env:BAILIAN_MODEL) { $env:BAILIAN_MODEL = "deepseek-v4-flash-0731" }
Write-Output "Requesting 400 development rows. Expect 25 to 45 minutes. Do not print the key."
python evaluation\run_evaluation.py --system deepseek-raw --input evaluation\data\development\development-v1.jsonl --run 1 --output evaluation\experiments\raw-responses\development-run1.jsonl
if ($LASTEXITCODE -ne 0) { throw "Bailian request failed." }
python evaluation\run_evaluation.py --system deepseek-only --input evaluation\data\development\development-v1.jsonl --raw evaluation\experiments\raw-responses\development-run1.jsonl --output evaluation\experiments\deepseek-only\development-v1.jsonl
python evaluation\run_evaluation.py --system plus-evidence --input evaluation\data\development\development-v1.jsonl --raw evaluation\experiments\raw-responses\development-run1.jsonl --output evaluation\experiments\plus-evidence\development-v1.jsonl
python evaluation\run_evaluation.py --system plus-target --input evaluation\data\development\development-v1.jsonl --raw evaluation\experiments\raw-responses\development-run1.jsonl --output evaluation\experiments\plus-target\development-v1.jsonl
python evaluation\run_evaluation.py --system full-system --input evaluation\data\development\development-v1.jsonl --raw evaluation\experiments\raw-responses\development-run1.jsonl --output evaluation\experiments\full-system\development-v1.jsonl
foreach ($name in @("deepseek-only", "plus-evidence", "plus-target", "full-system")) {
    python evaluation\score_predictions.py --gold evaluation\data\development\development-v1.jsonl --predictions "evaluation\experiments\$name\development-v1.jsonl" --output "evaluation\experiments\$name\development-v1-score.json"
}
Write-Output "Development run finished."
