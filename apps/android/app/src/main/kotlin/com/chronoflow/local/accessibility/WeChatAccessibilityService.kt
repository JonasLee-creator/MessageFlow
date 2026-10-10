package com.chronoflow.local.accessibility

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Build
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.chronoflow.local.ChronoApplication
import com.chronoflow.local.domain.ForegroundCaptureGuard
import com.chronoflow.local.domain.Incoming
import com.chronoflow.local.domain.NotificationMatcher
import com.chronoflow.local.domain.Source
import java.time.Instant
import java.util.ArrayDeque
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Opt-in foreground capture for WeChat group chats whose visible title exactly matches a whitelist entry.
 * The service never clicks, scrolls, types, or performs gestures. A newly opened chat is used only as a
 * baseline; only text that appears afterwards can enter the existing review pipeline.
 */
class WeChatAccessibilityService : AccessibilityService() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var pending: Job? = null
    private var ignoreHistoryUntil = 0L
    private var activeGroup: String? = null
    private val seen = LinkedHashSet<String>()

    private val app: ChronoApplication get() = application as ChronoApplication

    override fun onServiceConnected() {
        serviceScope.launch {
            runCatching { app.repository.awaitReady() }
            updateStatus(
                if (app.repository.state.value.preferences.accessibilityCaptureEnabled)
                    "无障碍服务已连接；等待打开微信白名单群"
                else "系统无障碍服务已连接；App 内采集开关仍关闭"
            )
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.packageName?.toString() != Source.WECHAT.packageName) return
        pending?.cancel()
        // Upward scrolling exposes older history. A positive/zero delta can also be WeChat
        // automatically moving to a newly arrived message and must still be inspected.
        val upwardScroll = event.eventType == AccessibilityEvent.TYPE_VIEW_SCROLLED &&
            Build.VERSION.SDK_INT >= 28 && event.scrollDeltaY < 0
        if (upwardScroll) ignoreHistoryUntil = SystemClock.uptimeMillis() + 1_200
        val historicalScroll = SystemClock.uptimeMillis() < ignoreHistoryUntil
        pending = serviceScope.launch {
            delay(350)
            runCatching { inspectVisibleChat(historicalScroll) }
                .onFailure { updateStatus("微信前台采集暂时失败：${it.message.orEmpty().take(80)}") }
        }
    }

    private suspend fun inspectVisibleChat(historicalScroll: Boolean) {
        app.repository.awaitReady()
        val preferences = app.repository.state.value.preferences
        if (!preferences.accessibilityCaptureEnabled) {
            resetConversation()
            return
        }

        val root = rootInActiveWindow ?: return
        if (root.packageName?.toString() != Source.WECHAT.packageName) return
        val rootBounds = Rect().also(root::getBoundsInScreen)
        if (rootBounds.height() <= 0) return

        // Only the top app-bar-sized region is read before authorization by whitelist title.
        val headerBottom = rootBounds.top + (120 * resources.displayMetrics.density).toInt()
        val headerTexts = collectText(root) { node, bounds ->
            node.isVisibleToUser && bounds.top >= rootBounds.top && bounds.bottom <= headerBottom && !node.isEditable
        }
        val group = ForegroundCaptureGuard.allowedGroup(headerTexts, preferences)
        if (group == null) {
            resetConversation()
            updateStatus("微信当前页面未匹配白名单群；未读取消息区")
            return
        }

        val messageBottom = rootBounds.top + (rootBounds.height() * 0.88f).toInt()
        val visible = ForegroundCaptureGuard.messageCandidates(
            collectText(root) { node, bounds ->
                node.isVisibleToUser && bounds.top >= headerBottom && bounds.bottom <= messageBottom &&
                    !node.isEditable && node.className?.toString()?.contains("EditText", ignoreCase = true) != true
            },
            group,
        )

        if (activeGroup != group || historicalScroll) {
            activeGroup = group
            remember(visible)
            updateStatus(if (historicalScroll) "已忽略向上滚动显示的历史内容：$group" else "已进入白名单群并建立基线：$group")
            return
        }

        val fresh = visible.filterNot(seen::contains)
        remember(visible)
        if (fresh.isEmpty()) return

        val accepted = fresh.filter { preferences.aiEnabled || NotificationMatcher.relevant(it) }
        if (accepted.isEmpty()) {
            updateStatus("$group 出现新文字，但未发现任务或日程关键词")
            return
        }
        updateStatus("已从 $group 捕捉 ${accepted.size} 条新文字，正在分析")
        accepted.forEach { content ->
            app.repository.accessibility(
                Incoming(
                    source = Source.WECHAT,
                    group = group,
                    content = content,
                    receivedAt = Instant.now(),
                    sourceKey = "accessibility|$group|${content.hashCode()}",
                )
            )
        }
        updateStatus("已从 $group 捕捉并分析 ${accepted.size} 条新文字")
    }

    private fun collectText(
        root: AccessibilityNodeInfo,
        include: (AccessibilityNodeInfo, Rect) -> Boolean,
    ): List<String> {
        val result = ArrayList<String>()
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        var visited = 0
        while (queue.isNotEmpty() && visited++ < 2_000) {
            val node = queue.removeFirst()
            val bounds = Rect().also(node::getBoundsInScreen)
            if (include(node, bounds)) {
                node.text?.toString()?.trim()?.takeIf(String::isNotEmpty)?.let(result::add)
                node.contentDescription?.toString()?.trim()?.takeIf(String::isNotEmpty)?.let(result::add)
            }
            for (index in 0 until node.childCount) node.getChild(index)?.let(queue::addLast)
        }
        return result
    }

    private fun remember(values: Collection<String>) {
        seen.addAll(values)
        while (seen.size > 800) seen.iterator().run { next(); remove() }
    }

    private fun resetConversation() {
        activeGroup = null
        seen.clear()
    }

    private fun updateStatus(message: String) {
        app.repository.lastAccessibilityCapture.value = message
    }

    override fun onInterrupt() {
        updateStatus("无障碍服务已中断")
    }

    override fun onDestroy() {
        pending?.cancel()
        serviceScope.cancel()
        super.onDestroy()
    }
}
