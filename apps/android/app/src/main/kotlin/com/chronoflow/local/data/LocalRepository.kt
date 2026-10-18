package com.chronoflow.local.data

import android.content.Context
import com.chronoflow.local.ai.AiClient
import com.chronoflow.local.BuildConfig
import com.chronoflow.local.notifications.Reminders
import com.chronoflow.local.canvas.CanvasClient
import com.chronoflow.local.domain.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import java.time.ZoneId

class LocalRepository(context: Context) {
    private val appContext = context.applicationContext
    private val accounts = AccountStore(appContext)
    private var store = EncryptedStore(appContext)
    private val deepSeek = AiClient()
    private val canvas = CanvasClient()
    private val modelPlanner = com.chronoflow.local.model.ModelPlannerClient(appContext)
    val modelStatus = MutableStateFlow("尚未生成智能计划")
    private val mutex = Mutex()
    private val canvasMutex = Mutex()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutable = MutableStateFlow(LocalState())
    val state = mutable.asStateFlow()
    private val mutableSession = MutableStateFlow<LocalSession?>(null)
    val session = mutableSession.asStateFlow()
    private val mutableWorkspace = MutableStateFlow(WorkspaceSnapshot())
    val workspace = mutableWorkspace.asStateFlow()
    val initialized = MutableStateFlow(false)
    val apiStatus = MutableStateFlow("接口未测试")
    @Volatile private var generation = 0L
    val workspaceVersion: Long get() = generation
    private fun publish(next: LocalState, owner: LocalSession? = mutableSession.value) {
        mutable.value = next; mutableSession.value = owner; mutableWorkspace.value = WorkspaceSnapshot(owner, next, generation)
    }
    private fun deploymentPolicy(value: LocalState): LocalState = if (!BuildConfig.ALLOW_OFFICIAL_API && value.preferences.aiApiMode == ApiMode.OFFICIAL)
        value.copy(preferences = value.preferences.copy(aiEnabled = false, aiApiMode = ApiMode.USER, officialAccessCode = "")) else value
    val storageError = MutableStateFlow<String?>(null)
    val aiError = MutableStateFlow<String?>(null)
    val lastNotification = MutableStateFlow("尚未收到微信或 QQ 通知")
    val canvasStatus = MutableStateFlow("尚未连接 Canvas")
    private val ready = scope.async {
        try {
            val owner = accounts.activeSession()
            store = EncryptedStore(appContext, owner?.userId)
            if (owner != null) {
                val loaded = store.load(); val next = deploymentPolicy(loaded)
                if (next != loaded) store.save(next)
                generation++; publish(next, owner)
            }
            if (mutable.value.preferences.canvasEnabled) canvasStatus.value = "Canvas 已连接，等待同步"
        }
        catch (e: Exception) { storageError.value = "本地数据读取失败，已停止写入以保护文件。请勿清除应用数据。"; throw e }
        finally { initialized.value = true }
    }
    suspend fun awaitReady() { ready.await() }
    suspend fun generateModelPlan() = withContext(Dispatchers.IO) {
        awaitReady()
        val ownerVersion = generation
        val snapshot = mutable.value
        require(mutableSession.value != null) { "请先进入工作空间" }
        modelStatus.value = "正在为你安排时间…"
        try {
            val schedule = modelPlanner.plan(snapshot)
            mutex.withLock {
                require(generation == ownerVersion && mutable.value == snapshot && snapshot.preferences.localModelEnabled) { "工作空间或任务已变化，请重新生成" }
                val next = snapshot.copy(schedule = schedule)
                store.save(next); publish(next)
                modelStatus.value = "智能计划已生成"
            }
        } catch (e: Exception) {
            if (generation == ownerVersion) modelStatus.value = "模型规划未完成，原计划保留"
            throw e
        }
    }
    suspend fun withCurrentWorkspace(version: Long, action: (LocalSession?, LocalState) -> Unit) = withContext(Dispatchers.IO) {
        ready.await()
        mutex.withLock { if (generation == version) action(mutableSession.value, mutable.value) }
    }
    suspend fun change(replan: Boolean = false, expectedGeneration: Long? = null, edit: (LocalState) -> LocalState) = withContext(Dispatchers.IO) {
        ready.await()
        mutex.withLock {
            if (mutableSession.value == null || (expectedGeneration != null && generation != expectedGeneration)) return@withLock
            var next = edit(mutable.value)
            val before = mutable.value
            if (replan || next.schedule != before.schedule) {
                // LocalEngine returns a provisional basic plan. Do not treat its
                // newly generated blocks as commitments for the model.
                val commitments = if (next.executionHistory != before.executionHistory) next.schedule
                    else if (next.tasks != before.tasks || next.events != before.events) before.schedule else next.schedule
                val input = next.copy(schedule = commitments)
                next = if (next.preferences.localModelEnabled && next.tasks.any { it.status == TaskStatus.ACTIVE && it.remaining > 0 }) {
                    modelStatus.value = "正在手机内生成计划…"
                    try {
                        val planned = modelPlanner.plan(input)
                        modelStatus.value = "本机智能计划已生成"
                        next.copy(schedule = planned)
                    } catch (e: Exception) {
                        // Data edits are still saved. The UI explicitly identifies
                        // this fallback as a basic plan, never a model result.
                        modelStatus.value = "本机模型未完成，当前使用基础排程。可在首页重试。"
                        next.copy(schedule = LocalScheduler.plan(input, Instant.now()))
                    }
                } else {
                    modelStatus.value = if (next.preferences.localModelEnabled) "添加任务后即可使用本机模型" else "本机模型已关闭，当前使用基础排程"
                    next.copy(schedule = LocalScheduler.plan(input, Instant.now()))
                }
            }
            if (next != mutable.value) {
                store.save(next) // Publish only after a successful atomic save.
                publish(next)
            }
        }
    }
    private suspend fun openWorkspace(select: () -> LocalSession) = withContext(Dispatchers.IO) {
        ready.await()
        mutex.withLock {
            val owner = select()
            val nextStore = EncryptedStore(appContext, owner.userId)
            val previous = nextStore.load()
            val loaded = deploymentPolicy(previous)
            val next = loaded
            if (next != previous) nextStore.save(next)
            accounts.rememberSession(owner)
            generation++; store = nextStore
            runCatching { Reminders.clear(appContext) }
            aiError.value = null; apiStatus.value = "接口未测试"
            modelStatus.value = if (next.schedule.engine == "chronoflow-local") "已恢复本机智能计划" else "添加任务后生成本机智能计划"
            lastNotification.value = "等待当前工作空间的群通知"
            canvasStatus.value = if (next.preferences.canvasEnabled) "Canvas 已连接，可立即同步" else "未连接 Canvas"
            publish(next, owner)
        }
    }
    suspend fun login(username: String, password: String) = openWorkspace { accounts.login(username, password) }
    suspend fun register(username: String, password: String, confirmation: String) = openWorkspace { accounts.register(username, password, confirmation) }
    suspend fun enterGuest() = openWorkspace { LocalSession() }
    suspend fun logout() = withContext(Dispatchers.IO) {
        ready.await()
        mutex.withLock {
            if (mutableSession.value == null) return@withLock
            val cleared = mutable.value.copy(preferences = mutable.value.preferences.copy(aiEnabled = false, deepSeekApiKey = "", officialAccessCode = ""))
            store.save(cleared); publish(cleared)
            accounts.rememberSession(null); generation++
            runCatching { Reminders.clear(appContext) }
            publish(LocalState(), null)
            aiError.value = null; apiStatus.value = "接口未测试"; canvasStatus.value = "未连接 Canvas"
        }
    }
    suspend fun testApi(p: Preferences) {
        awaitReady()
        if (mutableSession.value == null) return
        val version = generation
        apiStatus.value = "正在测试连接…"
        try {
            val result = deepSeek.test(p.copy(aiEnabled = true))
            if (generation == version && mutableSession.value != null) apiStatus.value = result
        } catch (e: Exception) {
            if (generation == version && mutableSession.value != null) apiStatus.value = "连接测试失败，请检查配置"
            throw e
        }
    }
    suspend fun receive(envelope: NotificationEnvelope) {
        awaitReady()
        if (mutableSession.value == null || !mutable.value.preferences.enabled) return
        val version = generation
        val inputs = NotificationMatcher.extract(envelope, mutable.value.preferences)
        val app = when (envelope.packageName) { Source.WECHAT.packageName -> "微信"; Source.QQ.packageName -> "QQ"; else -> envelope.packageName }
        val identity = listOf(envelope.conversationTitle, envelope.title, envelope.subText).firstOrNull { it.isNotBlank() }.orEmpty()
        if (generation != version) return
        lastNotification.value = when {
            !mutable.value.preferences.enabled -> "已收到$app 通知，但“开始采集群通知”尚未开启"
            inputs.isEmpty() -> "已收到$app 通知（$identity），但未匹配白名单群名或任务关键词"
            else -> "已捕捉$app 通知（$identity），生成 ${inputs.size} 条待分析内容"
        }
        inputs.forEach { smartIngest(it, version) }
    }
    suspend fun manual(input: Incoming) = smartIngest(input)
    private suspend fun smartIngest(input: Incoming, expected: Long = generation) {
        awaitReady()
        if (mutableSession.value == null || generation != expected) return
        val snapshot = mutable.value
        val proposals = if (snapshot.preferences.aiEnabled) {
            runCatching { deepSeek.analyze(input, snapshot) }.fold(
                onSuccess = { if (generation == expected) aiError.value = null; it },
                onFailure = { if (generation == expected) aiError.value = "AI 分析失败，已使用本地规则；没有切换接口。${it.message.orEmpty().take(160)}"; listOf(LocalParser.parse(input, snapshot)) },
            )
        } else listOf(LocalParser.parse(input, snapshot))
        change(expectedGeneration = expected) { LocalEngine.ingestAnalyzed(it, input, proposals, Instant.now()) }
    }

    suspend fun reanalyzeNotice(id: String) {
        awaitReady()
        val version = generation
        val snapshot = mutable.value
        val old = snapshot.notices.firstOrNull { it.id == id } ?: error("通知不存在")
        require(old.status == NoticeStatus.REVIEW) { "只能重新分析待确认通知" }
        val proposals = deepSeek.analyze(old.input, snapshot)
        change(expectedGeneration = version) { current ->
            val existing = current.notices.firstOrNull { it.id == id } ?: error("通知不存在")
            require(existing.status == NoticeStatus.REVIEW) { "通知已经处理" }
            val replacements = proposals.take(10).mapIndexed { index, proposal -> Notice(
                id = if (index == 0) existing.id else newId(),
                input = existing.input.copy(sourceKey = existing.input.sourceKey.substringBefore("#") + if (proposals.size > 1) "#${index + 1}" else ""),
                proposal = proposal, status = if (proposal.action == Action.IGNORE) NoticeStatus.IGNORED else NoticeStatus.REVIEW,
            ) }
            current.copy(notices = current.notices.flatMap { if (it.id == id) replacements else listOf(it) }.take(1000))
        }
        if (generation == version) aiError.value = null
    }

    suspend fun generateReport(type: AiReportType) {
        awaitReady()
        val version = generation
        val report = deepSeek.report(mutable.value, type)
        change(expectedGeneration = version) { state -> state.copy(aiReports = (listOf(report) + state.aiReports).take(30)) }
        if (generation == version) aiError.value = null
    }
    suspend fun review(id: String, proposal: Proposal) = change { LocalEngine.apply(it, id, proposal, Instant.now()) }
    suspend fun saveTask(task: Task) = change { LocalEngine.saveTask(it, task, Instant.now()) }
    suspend fun completeTask(id: String, cancel: Boolean = false) {
        val now = Instant.now()
        change(replan = true) { s -> s.copy(tasks = s.tasks.map { t ->
            if (t.id != id) t else t.copy(status = if (cancel) TaskStatus.CANCELLED else TaskStatus.COMPLETED,
                remaining = if (cancel) t.remaining else 0, completedAt = if (cancel) null else now)
        }) }
    }
    suspend fun toggleSubTask(taskId: String, subTaskId: String) = change { state -> state.copy(tasks = state.tasks.map { task ->
        if (task.id != taskId) task else task.copy(subTasks = task.subTasks.map { sub -> if (sub.id != subTaskId) sub else sub.copy(done = !sub.done) })
    }) }
    suspend fun saveEvent(event: FixedEvent) = change { LocalEngine.saveEvent(it, event, Instant.now()) }
    suspend fun cancelEvent(id: String) = change(replan = true) { it.copy(events = it.events.filterNot { e -> e.id == id }) }
    suspend fun lock(id: String) = change(replan = true) { it.copy(schedule = it.schedule.copy(blocks = it.schedule.blocks.map { b -> if (b.id != id) b else b.copy(locked = !b.locked) })) }
    suspend fun recordExecution(blockId: String, outcome: ExecutionOutcome, actualMinutes: Int? = null) =
        change(replan = true) { PersonalTimeModel.record(it, blockId, outcome, actualMinutes, Instant.now()) }
    suspend fun configureCanvas(baseUrl: String, accessToken: String) {
        awaitReady()
        val normalized = CanvasClient.normalizeBaseUrl(baseUrl)
        CanvasClient.validateToken(accessToken)
        preferences(mutable.value.preferences.copy(canvasEnabled = true, canvasBaseUrl = normalized, canvasAccessToken = accessToken))
        syncCanvas()
    }
    suspend fun disconnectCanvas() {
        awaitReady()
        preferences(mutable.value.preferences.copy(canvasEnabled = false, canvasBaseUrl = "", canvasAccessToken = ""))
        canvasStatus.value = "尚未连接 Canvas"
    }
    suspend fun syncCanvas() = canvasMutex.withLock {
        awaitReady()
        if (mutableSession.value == null) return@withLock
        val version = generation
        val p = mutable.value.preferences
        require(p.canvasEnabled) { "请先连接 Canvas" }
        canvasStatus.value = "正在从 Canvas 同步课程、作业、公告和日历…"
        try {
            val payload = canvas.sync(p.canvasBaseUrl, p.canvasAccessToken)
            var stats = CanvasMergeStats()
            change(expectedGeneration = version) { state -> CanvasSyncEngine.merge(state, payload.items, Instant.now()).also { stats = it.stats }.state }
            if (generation == version) canvasStatus.value = "同步完成：${payload.courseCount} 门课程，新增 ${stats.added} 条，更新 ${stats.updated} 条，未变化 ${stats.unchanged} 条"
        } catch (e: Exception) {
            if (generation == version) canvasStatus.value = "同步失败：${e.message.orEmpty().take(180)}"
            throw e
        }
    }
    suspend fun preferences(p: Preferences) = change(replan = true) {
        require(p.startHour in 0..23 && p.endHour in 1..24 && p.endHour > p.startHour) { "请设置有效的每日可用时间" }
        ZoneId.of(p.zone)
        require(p.groups.all { g -> g.source in listOf(Source.WECHAT, Source.QQ) && g.name.isNotBlank() && g.name.length <= 100 }) { "群名无效" }
        require(!p.enabled || p.groups.isNotEmpty()) { "请先添加群名白名单" }
        AiApiPolicy.validate(p, BuildConfig.ALLOW_OFFICIAL_API)
        if (p.canvasEnabled) {
            CanvasClient.normalizeBaseUrl(p.canvasBaseUrl)
            CanvasClient.validateToken(p.canvasAccessToken)
        }
        val old = it.preferences
        if (old.aiApiMode != p.aiApiMode || old.aiBaseUrl != p.aiBaseUrl || old.deepSeekModel != p.deepSeekModel ||
            old.deepSeekApiKey != p.deepSeekApiKey || old.officialGatewayUrl != p.officialGatewayUrl || old.officialAccessCode != p.officialAccessCode)
            apiStatus.value = "接口未测试"
        it.copy(preferences = p.copy(groups = p.groups.distinct()))
    }
}
