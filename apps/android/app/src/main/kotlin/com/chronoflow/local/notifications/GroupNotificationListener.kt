package com.chronoflow.local.notifications

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.chronoflow.local.ChronoApplication
import com.chronoflow.local.domain.*
import kotlinx.coroutines.launch

class GroupNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName !in listOf(Source.WECHAT.packageName, Source.QQ.packageName)) return
        val extras = sbn.notification.extras
        // Framework notifications store MessagingStyle messages in EXTRA_MESSAGES.
        val messages = runCatching {
            extras.getParcelableArray(Notification.EXTRA_MESSAGES)?.let { bundles ->
                Notification.MessagingStyle.Message.getMessagesFromBundleArray(bundles)
            }.orEmpty()
        }.getOrDefault(emptyList())
        val envelope = NotificationEnvelope(
            packageName = sbn.packageName, key = sbn.key, postedAt = sbn.postTime,
            title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty(),
            conversationTitle = extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString().orEmpty(),
            text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty(),
            bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty(),
            lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)?.map { it.toString() }.orEmpty(),
            messages = messages.map { MessagePart(it.text?.toString().orEmpty(), it.sender?.toString().orEmpty(), it.timestamp) },
            summary = sbn.notification.flags and Notification.FLAG_GROUP_SUMMARY != 0,
            subText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString().orEmpty(),
        )
        val app = application as ChronoApplication
        app.scope.launch {
            runCatching { app.repository.receive(envelope) }.onFailure {
                app.repository.storageError.value = "通知保存失败，请打开应用查看本地存储状态。"
            }
        }
    }
}
