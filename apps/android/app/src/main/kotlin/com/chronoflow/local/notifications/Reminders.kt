package com.chronoflow.local.notifications

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.os.Build
import com.chronoflow.local.ChronoApplication
import com.chronoflow.local.MainActivity
import com.chronoflow.local.R
import com.chronoflow.local.domain.*
import kotlinx.coroutines.launch
import java.time.Instant

object Reminders {
    private const val CHANNEL = "schedule"
    fun createChannel(context: Context) {
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "日程开始提醒", NotificationManager.IMPORTANCE_DEFAULT).apply { description = "本地任务与固定日程开始时提醒" })
    }
    fun allowed(context: Context): Boolean = (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
        context.getSystemService(NotificationManager::class.java).areNotificationsEnabled()

    fun arm(context: Context, state: LocalState) {
        val intent = PendingIntent.getBroadcast(context, 1, Intent(context, ReminderReceiver::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val alarm = context.getSystemService(AlarmManager::class.java)
        alarm.cancel(intent)
        val now = Instant.now()
        val next = ReminderPlan.pending(state, now).firstOrNull() ?: return
        // Inexact alarm: does not request exact-alarm special access.
        alarm.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, maxOf(next.start.toEpochMilli(), now.plusSeconds(2).toEpochMilli()), intent)
    }

    suspend fun deliver(context: Context) {
        val app = context.applicationContext as ChronoApplication
        app.repository.awaitReady()
        var due = emptyList<ReminderItem>()
        app.repository.change { state ->
            due = ReminderPlan.pending(state, Instant.now()).filter { it.start <= Instant.now() }
            state.copy(reminded = (state.reminded + due.map { it.key }).toList().takeLast(512).toSet())
        }
        if (allowed(context)) {
            val tap = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            due.forEach { item ->
                val notification = Notification.Builder(context, CHANNEL).setSmallIcon(R.drawable.ic_reminder)
                    .setContentTitle(item.title).setContentText("计划时间到了，打开时序查看安排")
                    .setContentIntent(tap).setAutoCancel(true).build()
                context.getSystemService(NotificationManager::class.java).notify(item.key.hashCode(), notification)
            }
        }
        arm(context, app.repository.state.value)
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        val app = context.applicationContext as ChronoApplication
        app.scope.launch { try {
            runCatching { Reminders.deliver(context) }.onFailure { app.repository.storageError.value = "本地提醒未完成，请打开应用检查设置。" }
        } finally { pending.finish() } }
    }
}

class RestoreRemindersReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        val app = context.applicationContext as ChronoApplication
        app.scope.launch { try {
            runCatching {
                app.repository.awaitReady()
                app.repository.change(replan = true) { it }
                Reminders.arm(context, app.repository.state.value)
            }.onFailure { app.repository.storageError.value = "重新安排提醒失败，请打开应用重试。" }
        } finally { pending.finish() } }
    }
}
