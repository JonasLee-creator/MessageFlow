param(
    [string]$KotlinHome = 'D:\Program Files\IntelliJ IDEA\IntelliJ IDEA 2025.3.3\plugins\Kotlin\kotlinc',
    [string]$Java = 'java'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$domain = Join-Path $root 'apps\android\app\src\main\kotlin\com\chronoflow\local\domain'
$test = Join-Path $root 'apps\android\app\src\test\kotlin\com\chronoflow\local\CoreChecks.kt'
$outputDirectory = Join-Path $root '.checks'
if (-not (Test-Path -LiteralPath (Join-Path $KotlinHome 'lib\kotlin-compiler.jar'))) { throw 'Supply an existing KotlinHome. This script does not install anything.' }
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$outputJar = Join-Path $outputDirectory 'local-core-tests.jar'
$sources = @(Get-ChildItem -LiteralPath $domain -Filter '*.kt' | ForEach-Object { $_.FullName }) + @($test)
& $Java -cp (Join-Path $KotlinHome 'lib\*') org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -kotlin-home $KotlinHome -jvm-target 17 @sources -include-runtime -d $outputJar
if ($LASTEXITCODE -ne 0) { throw 'Kotlin compilation failed.' }
& $Java -cp $outputJar com.chronoflow.local.CoreChecks
if ($LASTEXITCODE -ne 0) { throw 'Core regression failed.' }
