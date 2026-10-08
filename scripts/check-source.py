"""Dependency-light checks. Does not install packages or claim a successful build."""
import ast
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
failures = []
py_files = list((ROOT / "services").rglob("*.py")) + list((ROOT / "scripts").glob("*.py"))
xml_files = list((ROOT / "apps/mobile/android").rglob("*.xml"))
for path in py_files:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        failures.append(str(exc))
for path in xml_files:
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        failures.append(f"{path}: {exc}")

# Cross-language MethodChannel contract; not a Dart/Kotlin compiler substitute.
dart = (ROOT / "apps/mobile/lib/services/native_bridge.dart").read_text(encoding="utf-8")
kotlin = (ROOT / "apps/mobile/android/app/src/main/kotlin/com/chronoflow/app/MainActivity.kt").read_text(encoding="utf-8")
methods = re.findall(r"invokeMethod\('([^']+)'", dart)
for method in methods:
    if f'"{method}" ->' not in kotlin:
        failures.append(f"Missing native handler: {method}")
if "com.chronoflow/notifications" not in kotlin or "com.chronoflow/notifications" not in dart:
    failures.append("Channel names disagree")

manifest = ET.parse(ROOT / "apps/mobile/android/app/src/main/AndroidManifest.xml")
android = "{http://schemas.android.com/apk/res/android}"
service = manifest.find("application/service")
if service is None or service.get(android + "permission") != "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE":
    failures.append("Notification service binding permission missing")
if manifest.find("application").get(android + "usesCleartextTraffic") != "false":
    failures.append("Release manifest must not enable cleartext traffic")

print(f"Python syntax: {len(py_files)} files")
print(f"Android XML: {len(xml_files)} files")
print(f"Flutter/Kotlin bridge: {len(methods)} methods")
for failure in failures:
    print("FAIL:", failure)
print("Source checks passed. APK compilation and integration tests are separate." if not failures else "Source checks failed.")
sys.exit(bool(failures))
