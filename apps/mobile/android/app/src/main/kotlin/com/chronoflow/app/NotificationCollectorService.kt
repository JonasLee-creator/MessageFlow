package com.chronoflow.app

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject
import java.security.MessageDigest
import java.time.Instant

class NotificationCollectorService : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName != "com.tencent.mm") return
        if (sbn.notification.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        val settings = SecureSettings(this)
        if (!settings.enabled || settings.token.isEmpty()) return
        val extras = sbn.notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim() ?: return
        if (title !in settings.groups) return
        val text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString()?.trim() ?: return
        if (text.isBlank() || text.length > 20000) return
        val keywords = listOf("作业", "实验", "项目", "报告", "考试", "提交", "截止", "延期", "改到", "提前", "推迟", "上课", "调课", "取消", "会议", "班会", "deadline", "assignment", "quiz", "meeting")
        if (keywords.none { text.contains(it, ignoreCase = true) }) return
        // Stable platform identity + exact body/time dedupes retries without collapsing revisions.
        val id = MessageDigest.getInstance("SHA-256").digest("${sbn.key}|${sbn.postTime}|$title|$text".toByteArray()).joinToString("") { "%02x".format(it) }
        val payload = JSONObject().put("platform", "wechat").put("source_type", "notification")
            .put("external_id", id).put("channel_name", title).put("title", title).put("content", text)
            .put("source_updated_at", Instant.ofEpochMilli(sbn.postTime).toString())
        runCatching {
            NotificationQueue(this).use { it.add(id, settings.encrypt(payload.toString())) }
            UploadWorker.enqueue(this)
        }.onFailure { settings.error("本地通知保存失败，请重新登录后重试。") }
    }
}
