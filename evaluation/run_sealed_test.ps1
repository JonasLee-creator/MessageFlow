$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $env:DASHSCOPE_API_KEY -or $env:DASHSCOPE_API_KEY.Length -lt 8) {
    throw "DASHSCOPE_API_KEY is missing in this window. Use the window where the key was entered."
}
if (-not $env:BAILIAN_CHAT_URL) { throw "BAILIAN_CHAT_URL is missing in this window." }
if (-not $env:BAILIAN_MODEL) { $env:BAILIAN_MODEL = "deepseek-v4-flash-0731" }

$inputFile = "evaluation\data\sealed-test\sealed-test-input.jsonl"
Write-Output "Sealed test started. Three model runs, about 15 to 25 minutes. Do not print the key."

python evaluation\run_evaluation.py --system rule-only --input $inputFile --output evaluation\experiments\rule-only\sealed-test.jsonl
if ($LASTEXITCODE -ne 0) { throw "Rule-only run failed." }

foreach ($run in 1, 2, 3) {
    python evaluation\run_evaluation.py --system deepseek-raw --input $inputFile --run $run --output "evaluation\experiments\raw-responses\sealed-run$run.jsonl"
    if ($LASTEXITCODE -ne 0) { throw "Bailian run $run failed." }
}

$raw = "evaluation\experiments\raw-responses\sealed-run1.jsonl"
python evaluation\run_evaluation.py --system deepseek-only --input $inputFile --raw $raw --output evaluation\experiments\deepseek-only\sealed-test.jsonl
python evaluation\run_evaluation.py --system plus-evidence --input $inputFile --raw $raw --output evaluation\experiments\plus-evidence\sealed-test.jsonl
python evaluation\run_evaluation.py --system plus-target --input $inputFile --raw $raw --output evaluation\experiments\plus-target\sealed-test.jsonl
python evaluation\run_evaluation.py --system full-system --input $inputFile --raw $raw --output evaluation\experiments\full-system\sealed-test.jsonl

$files = @(
    "evaluation\experiments\rule-only\sealed-test.jsonl",
    "evaluation\experiments\raw-responses\sealed-run1.jsonl",
    "evaluation\experiments\raw-responses\sealed-run2.jsonl",
    "evaluation\experiments\raw-responses\sealed-run3.jsonl",
    "evaluation\experiments\deepseek-only\sealed-test.jsonl",
    "evaluation\experiments\plus-evidence\sealed-test.jsonl",
    "evaluation\experiments\plus-target\sealed-test.jsonl",
    "evaluation\experiments\full-system\sealed-test.jsonl"
)
$hashLines = foreach ($file in $files) {
    $hash = Get-FileHash -Algorithm SHA256 -Path $file
    "{0}  {1}" -f $hash.Hash.ToLower(), $file
}
$hashPath = "evaluation\reports\sealed-prediction-hashes.txt"
Set-Content -Path $hashPath -Value $hashLines -Encoding ascii
Write-Output "Prediction hashes written. Scoring starts now. Do not rerun the model."

$gold = "evaluation\data\sealed-test\sealed-test-gold.jsonl"
foreach ($name in @("rule-only", "deepseek-only", "plus-evidence", "plus-target", "full-system")) {
    python evaluation\score_predictions.py --gold $gold --predictions "evaluation\experiments\$name\sealed-test.jsonl" --output "evaluation\experiments\$name\sealed-test-score.json"
}
Write-Output "Sealed test finished."
