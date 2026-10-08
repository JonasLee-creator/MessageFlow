# Run only AFTER the user installs Flutter and Android SDK.
# LEGACY Flutter only. Current native project: apps/android; see docs/ANDROID_LOCAL.md.
# Generates the official Gradle wrapper in a throwaway project and copies only
# wrapper launchers/JAR. Does not overwrite application or Kotlin source files.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$mobilePath = Join-Path $projectRoot 'apps\mobile'
$scaffoldPath = Join-Path $projectRoot '.tools\android-wrapper-template'
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw 'Flutter is not installed/on PATH. Follow docs/INSTALL.md first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $scaffoldPath 'android\gradlew.bat'))) {
    & flutter create --platforms=android --project-name chronoflow_wrapper --org com.chronoflow --no-pub $scaffoldPath
    if ($LASTEXITCODE -ne 0) { throw 'Flutter template generation failed.' }
}
$files = @('gradlew', 'gradlew.bat', 'gradle\wrapper\gradle-wrapper.jar')
foreach ($relative in $files) {
    $sourcePath = Join-Path $scaffoldPath "android\$relative"
    $destinationPath = Join-Path $mobilePath "android\$relative"
    if (-not (Test-Path -LiteralPath $sourcePath)) { throw "Missing official wrapper file: $sourcePath" }
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
}
Push-Location $mobilePath
try {
    & flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub get failed.' }
    Write-Output 'Android wrapper prepared. Next: flutter analyze; flutter test; flutter build apk --debug'
} finally { Pop-Location }
