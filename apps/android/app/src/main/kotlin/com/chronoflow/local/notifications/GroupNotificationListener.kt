package com.chronoflow.local.notifications

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import androidx.core.app.NotificationCompat
import com.chronoflow.local.ChronoApplication
import com.chronoflow.local.domain.*
import kotlinx.coroutines.launch

class GroupNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName !in listOf(Source.WECHAT.packageName, Source.QQ.packageName)) return
        val app = application as ChronoApplication
        if (app.repository.session.value == null || !app.repository.state.value.preferences.enabled) return
        val extras = sbn.notification.extras
        // AndroidX handles MessagingStyle extraction on every supported API.
        // The framework bundle-array helper is only public from API 30.
        val messages: List<NotificationCompat.MessagingStyle.Message> = runCatching {
            NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(sbn.notification)
                ?.messages.orEmpty()
        }.getOrDefault(emptyList())
        val envelope = NotificationEnvelope(
            packageName = sbn.packageName, key = sbn.key, postedAt = sbn.postTime,
            title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty(),
            conversationTitle = extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString().orEmpty(),
            text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty(),
            bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty(),
            lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)?.map { it.toString() }.orEmpty(),
            messages = messages.map { MessagePart(it.text?.toString().orEmpty(), it.person?.name?.toString().orEmpty(), it.timestamp) },
            summary = sbn.notification.flags and Notification.FLAG_GROUP_SUMMARY != 0,
            subText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString().orEmpty(),
        )
        app.scope.launch {
            runCatching { app.repository.receive(envelope) }.onFailure {
                app.repository.storageError.value = "通知保存失败，请打开应用查看本地存储状态。"
            }
        }
    }
}
