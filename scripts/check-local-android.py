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
domain = main / "kotlin/com/chronoflow/local/domain"
for file in domain.glob("*.kt"):
    assert "import android." not in file.read_text(encoding="utf-8")
print(f"{len(xmls)} Android XML files parse successfully")
print("Opt-in DeepSeek network permission present; no Flutter build dependency; backup disabled")
print("Notification binding, component sources and pure Kotlin domain checks passed")
print("This is not Gradle/Android compilation or real-device verification.")
