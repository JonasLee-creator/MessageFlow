package com.chronoflow.app

import android.content.ComponentName
import android.content.Intent
import android.provider.CalendarContract
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private fun hasAccess(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: ""
        val own = ComponentName(this, NotificationCollectorService::class.java)
        return enabled.split(":").any { ComponentName.unflattenFromString(it) == own }
    }
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.chronoflow/notifications").setMethodCallHandler { call, result ->
            try {
                val settings = SecureSettings(this)
                when (call.method) {
                    "getSettings" -> result.success(mapOf("baseUrl" to settings.baseUrl, "token" to settings.token,
                        "enabled" to settings.enabled, "groups" to settings.groups, "accessGranted" to hasAccess(),
                        "pendingCount" to NotificationQueue(this).use { it.count() }, "uploadError" to settings.uploadError))
                    "configure" -> {
                        val values = call.arguments as Map<*, *>
                        val accountChanged = (values.containsKey("token") && values["token"] != settings.token) || (values.containsKey("baseUrl") && values["baseUrl"] != settings.baseUrl)
                        if (accountChanged || values["enabled"] == false || values.containsKey("groups")) {
                            UploadWorker.stop(this)
                            NotificationQueue(this).use { it.clear() }
                            settings.error("")
                        }
                        settings.configure(values)
                        if (settings.enabled) UploadWorker.enqueue(this)
                        result.success(null)
                    }
                    "openNotificationAccess" -> {startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)); result.success(null)}
                    "retryUploads" -> {UploadWorker.enqueue(this); result.success(null)}
                    "exportCalendar" -> {
                        val intent = Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
                            .putExtra(CalendarContract.Events.TITLE, call.argument<String>("title"))
                            .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, call.argument<Number>("start")!!.toLong())
                            .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, call.argument<Number>("end")!!.toLong())
                        startActivity(intent); result.success(null)
                    }
                    else -> result.notImplemented()
                }
            } catch (_: Exception) {result.error("NATIVE_ERROR", "操作未完成，请检查系统设置或是否安装日历应用。", null)}
        }
    }
}
