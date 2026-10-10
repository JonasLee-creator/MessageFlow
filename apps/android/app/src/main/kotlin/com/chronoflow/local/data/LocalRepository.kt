package com.chronoflow.local.data

import android.content.Context
import com.chronoflow.local.ai.DeepSeekClient
import com.chronoflow.local.domain.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import java.time.ZoneId

class LocalRepository(context: Context) {
    private val store = EncryptedStore(context)
    private val deepSeek = DeepSeekClient()
    private val mutex = Mutex()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutable = MutableStateFlow(LocalState())
    val state = mutable.asStateFlow()
    val storageError = MutableStateFlow<String?>(null)
    val aiError = MutableStateFlow<String?>(null)
    val lastNotification = MutableStateFlow("尚未收到微信或 QQ 通知")
    val lastAccessibilityCapture = MutableStateFlow("尚未开始微信前台采集")
    private val ready = scope.async {
        try { mutable.value = store.load() }
        catch (e: Exception) { storageError.value = "本地数据读取失败，已停止写入以保护文件。请勿清除应用数据。"; throw e }
    }
    suspend fun awaitReady() { ready.await() }
    suspend fun change(replan: Boolean = false, edit: (LocalState) -> LocalState) = withContext(Dispatchers.IO) {
        ready.await()
        mutex.withLock {
            var next = edit(mutable.value)
            if (replan) next = next.copy(schedule = LocalScheduler.plan(next, Instant.now()))
            if (next != mutable.value) {
                store.save(next) // Publish only after a successful atomic save.
                mutable.value = next
            }
        }
    }
    suspend fun receive(envelope: NotificationEnvelope) {
        awaitReady()
        val inputs = NotificationMatcher.extract(envelope, mutable.value.preferences)
        val app = when (envelope.packageName) { Source.WECHAT.packageName -> "微信"; Source.QQ.packageName -> "QQ"; else -> envelope.packageName }
        val identity = listOf(envelope.conversationTitle, envelope.title, envelope.subText).firstOrNull { it.isNotBlank() }.orEmpty()
        lastNotification.value = when {
            !mutable.value.preferences.enabled -> "已收到$app 通知，但“开始采集群通知”尚未开启"
            inputs.isEmpty() -> "已收到$app 通知（$identity），但未匹配白名单群名或任务关键词"
            else -> "已捕捉$app 通知（$identity），生成 ${inputs.size} 条待分析内容"
        }
        inputs.forEach { smartIngest(it) }
    }
    suspend fun manual(input: Incoming) = smartIngest(input)
    suspend fun accessibility(input: Incoming) {
        require(input.source == Source.WECHAT) { "无障碍采集仅支持微信" }
        smartIngest(input)
    }
    private suspend fun smartIngest(input: Incoming) {
        awaitReady()
        val snapshot = mutable.value
        val proposals = if (snapshot.preferences.aiEnabled && snapshot.preferences.deepSeekApiKey.isNotBlank()) {
            runCatching { deepSeek.analyze(input, snapshot) }.fold(
                onSuccess = { aiError.value = null; it },
                onFailure = { aiError.value = "DeepSeek 分析失败，已使用本地规则：${it.message.orEmpty().take(160)}"; listOf(LocalParser.parse(input, snapshot)) },
            )
        } else listOf(LocalParser.parse(input, snapshot))
        change { LocalEngine.ingestAnalyzed(it, input, proposals, Instant.now()) }
    }

    suspend fun reanalyzeNotice(id: String) {
        awaitReady()
        val snapshot = mutable.value
        val old = snapshot.notices.firstOrNull { it.id == id } ?: error("通知不存在")
        require(old.status == NoticeStatus.REVIEW) { "只能重新分析待确认通知" }
        val proposals = deepSeek.analyze(old.input, snapshot)
        change { current ->
            val existing = current.notices.firstOrNull { it.id == id } ?: error("通知不存在")
            require(existing.status == NoticeStatus.REVIEW) { "通知已经处理" }
            val replacements = proposals.take(10).mapIndexed { index, proposal -> Notice(
                id = if (index == 0) existing.id else newId(),
                input = existing.input.copy(sourceKey = existing.input.sourceKey.substringBefore("#") + if (proposals.size > 1) "#${index + 1}" else ""),
                proposal = proposal, status = if (proposal.action == Action.IGNORE) NoticeStatus.IGNORED else NoticeStatus.REVIEW,
            ) }
            current.copy(notices = current.notices.flatMap { if (it.id == id) replacements else listOf(it) }.take(1000))
        }
        aiError.value = null
    }

    suspend fun generateReport(type: AiReportType) {
        awaitReady()
        val report = deepSeek.report(mutable.value, type)
        change { state -> state.copy(aiReports = (listOf(report) + state.aiReports).take(30)) }
        aiError.value = null
    }
    suspend fun review(id: String, proposal: Proposal) = change { LocalEngine.apply(it, id, proposal, Instant.now()) }
    suspend fun saveTask(task: Task) = change { LocalEngine.saveTask(it, task, Instant.now()) }
    suspend fun completeTask(id: String, cancel: Boolean = false) = change(replan = true) { s -> s.copy(tasks = s.tasks.map { t ->
        if (t.id != id) t else t.copy(status = if (cancel) TaskStatus.CANCELLED else TaskStatus.COMPLETED,
            remaining = if (cancel) t.remaining else 0, completedAt = if (cancel) null else Instant.now())
    }) }
    suspend fun toggleSubTask(taskId: String, subTaskId: String) = change { state -> state.copy(tasks = state.tasks.map { task ->
        if (task.id != taskId) task else task.copy(subTasks = task.subTasks.map { sub -> if (sub.id != subTaskId) sub else sub.copy(done = !sub.done) })
    }) }
    suspend fun saveEvent(event: FixedEvent) = change { LocalEngine.saveEvent(it, event, Instant.now()) }
    suspend fun cancelEvent(id: String) = change(replan = true) { it.copy(events = it.events.filterNot { e -> e.id == id }) }
    suspend fun lock(id: String) = change(replan = true) { it.copy(schedule = it.schedule.copy(blocks = it.schedule.blocks.map { b -> if (b.id != id) b else b.copy(locked = !b.locked) })) }
    suspend fun preferences(p: Preferences) = change(replan = true) {
        require(p.startHour in 0..23 && p.endHour in 1..24 && p.endHour > p.startHour) { "请设置有效的每日可用时间" }
        ZoneId.of(p.zone)
        require(p.groups.all { g -> g.source != Source.MANUAL && g.name.isNotBlank() && g.name.length <= 100 }) { "群名无效" }
        require(!p.enabled || p.groups.isNotEmpty()) { "请先添加群名白名单" }
        require(!p.accessibilityCaptureEnabled || p.groups.any { g -> g.source == Source.WECHAT }) { "微信前台采集需要至少一个微信白名单群" }
        require(!p.aiEnabled || p.deepSeekApiKey.length in 8..512) { "请填写有效的 DeepSeek API Key" }
        require(p.deepSeekModel.isNotBlank() && p.deepSeekModel.length <= 100 && p.deepSeekModel.none { c -> c.isWhitespace() }) { "DeepSeek 模型名称无效" }
        if (!p.accessibilityCaptureEnabled) lastAccessibilityCapture.value = "App 内微信前台采集开关已关闭"
        it.copy(preferences = p.copy(groups = p.groups.distinct()))
    }
}
