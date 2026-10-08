package com.chronoflow.app

import android.content.Context
import android.content.pm.ApplicationInfo
import androidx.work.*
import java.net.HttpURLConnection
import java.net.URI
import java.util.concurrent.TimeUnit

class UploadWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        val settings = SecureSettings(applicationContext)
        if (!settings.enabled || settings.token.isBlank()) return Result.success()
        val endpoint = settings.baseUrl
        val bearer = settings.token
        val uri = runCatching { URI(endpoint) }.getOrNull() ?: return Result.failure()
        val debug = applicationContext.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        if (uri.scheme != "https" && !(debug && uri.scheme == "http")) {
            settings.error("正式版通知上传需要 HTTPS 服务器。"); return Result.failure()
        }
        NotificationQueue(applicationContext).use { queue ->
            for ((id, encrypted) in queue.batch()) {
                if (isStopped || !settings.enabled || settings.token != bearer || settings.baseUrl != endpoint) return Result.success()
                var connection: HttpURLConnection? = null
                try {
                    val body = settings.decrypt(encrypted)
                    connection = URI("$endpoint/api/v1/ingest/notification").toURL().openConnection() as HttpURLConnection
                    connection.requestMethod = "POST"
                    connection.instanceFollowRedirects = false
                    connection.connectTimeout = 15000
                    connection.readTimeout = 90000
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    connection.setRequestProperty("Authorization", "Bearer $bearer")
                    connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                    val status = connection.responseCode
                    if (status in 200..299) {
                        queue.remove(id); settings.error("")
                    } else {
                        settings.error(if (status == 401) "登录已过期，请重新登录。" else "通知上传失败（$status），已保留待重试。")
                        return if (status == 401 || status in 400..499 && status != 429) Result.failure() else Result.retry()
                    }
                } catch (_: Exception) {
                    settings.error("网络暂不可用，通知将在恢复连接后重试。")
                    return Result.retry()
                } finally { connection?.disconnect() }
            }
            return if (queue.count() > 0) Result.retry() else Result.success()
        }
    }
    companion object {
        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS).build()
            WorkManager.getInstance(context).enqueueUniqueWork("chronoflow-notifications", ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }
        fun stop(context: Context) { WorkManager.getInstance(context).cancelUniqueWork("chronoflow-notifications") }
    }
}
