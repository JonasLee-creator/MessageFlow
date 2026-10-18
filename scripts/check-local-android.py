"""Static Android checks; does not install tools or replace an Android build."""
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
android = root / "apps/android"
main = android / "app/src/main"
xmls = list(main.rglob("*.xml"))
for file in xmls:
    ET.parse(file)
manifest = ET.parse(main / "AndroidManifest.xml").getroot()
ns = "{http://schemas.android.com/apk/res/android}"
permissions = {p.get(ns + "name") for p in manifest.findall("uses-permission")}
assert "android.permission.INTERNET" in permissions
assert manifest.find("application").get(ns + "allowBackup") == "false"
services = {service.get(ns + "name"): service for service in manifest.findall("application/service")}
notification_service = services[".notifications.GroupNotificationListener"]
assert notification_service.get(ns + "permission") == "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE"
assert notification_service.get(ns + "exported") == "false"
settings = (android / "settings.gradle.kts").read_text(encoding="utf-8")
build = (android / "app/build.gradle.kts").read_text(encoding="utf-8")
assert "flutter" not in settings.lower() + build.lower()
assert "org.jetbrains.kotlin.plugin.compose" in build
assert "minSdk = 26" in build
for relative in ["MainActivity.kt", "ChronoApplication.kt", "notifications/GroupNotificationListener.kt", "notifications/Reminders.kt"]:
    assert (main / "kotlin/com/chronoflow/local" / relative).is_file()
assert (main / "kotlin/com/chronoflow/local/canvas/CanvasClient.kt").is_file()
domain = main / "kotlin/com/chronoflow/local/domain"
for file in domain.glob("*.kt"):
    assert "import android." not in file.read_text(encoding="utf-8")
print(f"{len(xmls)} Android XML files parse successfully")
print("Opt-in DeepSeek/Canvas network permission present; no Flutter build dependency; backup disabled")
print("Notification binding, component sources and pure Kotlin domain checks passed")
import hashlib
import json
artifacts = root / "model/deployment/artifacts"
for name, digest in json.loads((artifacts / "checksums.json").read_text()).items():
    assert Path(name).name == name
    assert hashlib.sha256((artifacts / name).read_bytes()).hexdigest() == digest
client = (main / "kotlin/com/chronoflow/local/model/ModelPlannerClient.kt").read_text(encoding="utf-8")
assert "EmbeddedModelRuntime.plan" in client and "HttpURLConnection" not in client
assert 'id("com.chaquo.python") version "17.1.0"' in build and "onnxruntime-android" in build
assert 'id("com.chaquo.python")' not in (android / "build.gradle.kts").read_text(encoding="utf-8")
assert 'include("chronoflow_predictor.onnx"' in build
assert '"deployment/android.py"' in build
assert "dataset" not in build.split('val syncEmbeddedPython')[1].split('dependencies {')[0]
print("Bundled artifact checksums, offline entry and explicit production packaging checks passed")
print("This is not Gradle/Android compilation or real-device verification.")
