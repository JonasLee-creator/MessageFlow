$ErrorActionPreference = "Stop"
$KotlinHome = "C:\Program Files\Android\Android Studio\plugins\Kotlin\kotlinc"
$Java = "D:\Java\jdk-17\bin\java.exe"
$Root = Split-Path -Parent $PSScriptRoot
$Domain = Join-Path $Root "apps\android\app\src\main\kotlin\com\chronoflow\local\domain"
$Cli = Join-Path $PSScriptRoot "kotlin\EvaluationCli.kt"
$OutDir = Join-Path $Root ".checks"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$Jar = Join-Path $OutDir "evaluation-cli.jar"
$Sources = @(Get-ChildItem -LiteralPath $Domain -Filter "*.kt" | ForEach-Object { $_.FullName }) + @($Cli)
& $Java -cp (Join-Path $KotlinHome "lib\*") org.jetbrains.kotlin.cli.jvm.K2JVMCompiler `
    -kotlin-home $KotlinHome -jvm-target 17 @Sources -include-runtime -d $Jar
if ($LASTEXITCODE -ne 0) { throw "Evaluation runner compile failed." }
Write-Output "Wrote $Jar"
