package com.chronoflow.local.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.chronoflow.local.domain.*
import java.time.*
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun ChronoScreen(vm: AppViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val diskError by vm.repository.storageError.collectAsStateWithLifecycle()
    val aiError by vm.repository.aiError.collectAsStateWithLifecycle()
    val lastNotification by vm.repository.lastNotification.collectAsStateWithLifecycle()
    val canvasStatus by vm.repository.canvasStatus.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var editor by rememberSaveable { mutableStateOf<String?>(null) }
    var editTask by remember { mutableStateOf<Task?>(null) }
    var editEvent by remember { mutableStateOf<FixedEvent?>(null) }
    var review by remember { mutableStateOf<Notice?>(null) }
    var sources by remember { mutableStateOf<Task?>(null) }
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) { while (true) { now = Instant.now(); delay(30000) } }
    val zone = state.preferences.zone
    val today = now.atZone(ZoneId.of(zone)).toLocalDate()
    var dayOffset by rememberSaveable { mutableIntStateOf(0) }
    val labels = listOf("今天", "发现", "任务", "日历", "设置")
    val icons = listOf(Icons.Outlined.WbSunny, Icons.Outlined.Inbox, Icons.Outlined.Checklist, Icons.Outlined.CalendarMonth, Icons.Outlined.Tune)
    val pending = state.notices.count { it.status == NoticeStatus.REVIEW }
    Scaffold(
        topBar = { TopAppBar(title = { Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).background(Teal, RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.AllInclusive, null, tint = Color.White) }
            Spacer(Modifier.width(10.dp)); Text("时序", fontWeight = FontWeight.Bold); Spacer(Modifier.width(10.dp)); Text("本地日程", style = MaterialTheme.typography.labelMedium, color = Teal)
        } }, actions = { if (tab != 4) IconButton(onClick = { vm.run { vm.repository.change(replan = true) { it } } }, enabled = !busy) { Icon(Icons.Outlined.Refresh, "重新排程") } }) },
        bottomBar = { NavigationBar { labels.forEachIndexed { index, label -> NavigationBarItem(selected = index == tab, onClick = { tab = index }, icon = {
            if (index == 1 && pending > 0) BadgedBox(badge = { Badge { Text(pending.toString()) } }) { Icon(icons[index], label) }
            else Icon(icons[index], label)
        }, label = { Text(label) }) } } },
        floatingActionButton = { if (tab != 4 && !busy) ExtendedFloatingActionButton(onClick = {
            editTask = null; editEvent = null; editor = if (tab == 1) "message" else if (tab == 3) "event" else "task"
        }, icon = { Icon(if (tab == 1) Icons.Outlined.ContentPaste else Icons.Outlined.Add, null) }, text = { Text(if (tab == 1) "录入通知" else if (tab == 3) "固定日程" else "新建任务") }) },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            (diskError ?: error ?: aiError)?.let { message -> Surface(color = MaterialTheme.colorScheme.errorContainer) {
                Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(message, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                    if (diskError == null) IconButton(onClick = { vm.error.value = null; vm.repository.aiError.value = null }) { Icon(Icons.Outlined.Close, "关闭提示") }
                }
            } }
            when (tab) {
                0 -> TodayPage(state, today, now, busy, { tab = 1 }, { tab = 4 }) { type -> vm.run { vm.repository.generateReport(type) } }
                1 -> InboxPage(state, busy, onReview = { review = it },
                    onIgnore = { n -> vm.run { vm.repository.review(n.id, n.proposal.copy(action = Action.IGNORE)) } },
                    onReanalyze = { n -> vm.run { vm.repository.reanalyzeNotice(n.id) } })
                2 -> TasksPage(state, busy, onEdit = { editTask = it; editor = "task" }, onComplete = { vm.run { vm.repository.completeTask(it.id) } },
                    onCancel = { vm.run { vm.repository.completeTask(it.id, true) } }, onSources = { sources = it },
                    onToggleSubTask = { task, sub -> vm.run { vm.repository.toggleSubTask(task.id, sub.id) } })
                3 -> CalendarPage(state, today.plusDays(dayOffset.toLong()), dayOffset, { dayOffset = it }, busy,
                    onLock = { vm.run { vm.repository.lock(it.id) } },
                    onOutcome = { block, outcome -> vm.run { vm.repository.recordExecution(block.id, outcome) } },
                    onEditEvent = { editEvent = it; editor = "event" }, onCancelEvent = { vm.run { vm.repository.cancelEvent(it.id) } })
                4 -> SettingsPage(state.preferences, busy, lastNotification, canvasStatus,
                    onSave = { p -> vm.run { vm.repository.preferences(p) } },
                    onConnectCanvas = { url, token -> vm.run { vm.repository.configureCanvas(url, token) } },
                    onSyncCanvas = { vm.run { vm.repository.syncCanvas() } },
                    onDisconnectCanvas = { vm.run { vm.repository.disconnectCanvas() } })
            }
        }
    }
    when (editor) {
        "task" -> TaskEditor(editTask, state, { editor = null }) { task -> vm.run { vm.repository.saveTask(task) }; editor = null }
        "event" -> EventEditor(editEvent, zone, { editor = null }) { event -> vm.run { vm.repository.saveEvent(event) }; editor = null }
        "message" -> MessageEditor(state.preferences.aiEnabled, { editor = null }) { input -> vm.run { vm.repository.manual(input) }; editor = null; tab = 1 }
    }
    review?.let { notice -> ReviewEditor(notice, state, { review = null }) { proposal -> vm.run { vm.repository.review(notice.id, proposal) }; review = null } }
    sources?.let { task ->
        AlertDialog(onDismissRequest = { sources = null }, title = { Text("任务来源") }, text = {
            val notices = state.notices.filter { it.id in task.sourceIds }
            if (notices.isEmpty()) Text(if (task.sourceIds.isEmpty()) "手动创建的任务" else "较早的原始通知已超出本地保留数量")
            else LazyColumn { items(notices, key = { it.id }) { n -> Column(Modifier.padding(vertical = 8.dp)) { Text("${n.input.source.label} · ${n.input.group}", fontWeight = FontWeight.Bold); Text(n.input.content); Text(formatTime(n.input.receivedAt, zone), style = MaterialTheme.typography.labelSmall) } } }
        }, confirmButton = { TextButton(onClick = { sources = null }) { Text("关闭") } })
    }
}

@Composable fun PageHeading(eyebrow: String, title: String, subtitle: String) {
    Column(Modifier.padding(bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(eyebrow, style = MaterialTheme.typography.labelSmall, color = Teal, letterSpacing = 2.sp)
        Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = Muted)
    }
}
@Composable fun Panel(modifier: Modifier = Modifier, color: Color = Color.White, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), color = color, shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(9.dp), content = content)
    }
}
@Composable fun EmptyPanel(title: String, subtitle: String) {
    Panel { Icon(Icons.Outlined.Spa, null, tint = Teal); Text(title, fontWeight = FontWeight.Bold); Text(subtitle, color = Muted, style = MaterialTheme.typography.bodyMedium) }
}
@Composable fun RiskPanel(risk: Risk) {
    Panel(color = Color(0xFFFFEED7)) {
        Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Outlined.WarningAmber, null, tint = Color(0xFFA96628)); Spacer(Modifier.width(8.dp)); Text(risk.title, fontWeight = FontWeight.Bold) }
        Text(risk.message, style = MaterialTheme.typography.bodySmall)
        if (risk.missingMinutes > 0) Text("尚未安排 ${risk.missingMinutes} 分钟", fontWeight = FontWeight.Medium)
    }
}
private val pagePadding = PaddingValues(start = 20.dp, top = 20.dp, end = 20.dp, bottom = 100.dp)
private val gaps = Arrangement.spacedBy(14.dp)
private data class Entry(val title: String, val start: Instant, val end: Instant, val block: Block? = null, val event: FixedEvent? = null)
private fun entries(state: LocalState, date: LocalDate): List<Entry> {
    val start = date.atStartOfDay(ZoneId.of(state.preferences.zone)).toInstant()
    val end = date.plusDays(1).atStartOfDay(ZoneId.of(state.preferences.zone)).toInstant()
    val events = state.events.map { Entry(it.title, it.start, it.end, event = it) }
    val blocks = state.schedule.blocks.map { b -> Entry(state.tasks.firstOrNull { it.id == b.taskId }?.title ?: "任务", b.start, b.end, block = b) }
    return (events + blocks).filter { it.start < end && it.end > start }.sortedBy { it.start }
}
@Composable private fun Timeline(entry: Entry, zone: String, actions: @Composable () -> Unit = {}) {
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.width(58.dp)) { Text(formatTime(entry.start, zone, true), fontWeight = FontWeight.Bold); Text(formatTime(entry.end, zone, true), style = MaterialTheme.typography.labelSmall, color = Muted) }
            Box(Modifier.width(3.dp).height(44.dp).background(if (entry.event != null) Color(0xFFB68F4A) else Teal))
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(entry.title, fontWeight = FontWeight.Bold)
                Text(if (entry.event != null) "固定日程" else if (entry.block?.locked == true) "专注时间 · 已锁定" else "专注时间 · 可调整", color = Teal, style = MaterialTheme.typography.labelSmall)
                if (entry.start.atZone(ZoneId.of(zone)).toLocalDate() != entry.end.atZone(ZoneId.of(zone)).toLocalDate()) Text("${formatTime(entry.start, zone)} → ${formatTime(entry.end, zone)}", style = MaterialTheme.typography.labelSmall)
            }
        }
        actions()
    }
}

@Composable private fun TodayPage(state: LocalState, date: LocalDate, now: Instant, busy: Boolean, openInbox: () -> Unit, openSettings: () -> Unit, onReport: (AiReportType) -> Unit) {
    val rows = entries(state, date)
    val zone = ZoneId.of(state.preferences.zone)
    val dayStart = date.atStartOfDay(zone).toInstant(); val dayEnd = date.plusDays(1).atStartOfDay(zone).toInstant()
    val focus = rows.filter { it.block != null }.sumOf { Duration.between(maxOf(it.start, dayStart), minOf(it.end, dayEnd)).toMinutes() }
    val pending = state.notices.count { it.status == NoticeStatus.REVIEW }
    LazyColumn(contentPadding = pagePadding, verticalArrangement = gaps) {
        item { PageHeading(date.format(DateTimeFormatter.ofPattern("M月d日 EEEE", java.util.Locale.CHINA)), "把今天，安排从容。", "群里的重要消息，变成你的时间计划。") }
        item { Panel(color = Ink) {
            Text("你的今日节奏", color = Color(0xFFA4D9C2))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column { Text(rows.size.toString(), color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Bold); Text("日程安排", color = Color.White.copy(alpha = .7f), fontSize = 12.sp) }
                Column { Text("%.1f h".format(focus / 60.0), color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Bold); Text("计划专注", color = Color.White.copy(alpha = .7f), fontSize = 12.sp) }
                Column { Text(state.tasks.count { it.status == TaskStatus.ACTIVE }.toString(), color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Bold); Text("进行中", color = Color.White.copy(alpha = .7f), fontSize = 12.sp) }
            }
            HorizontalDivider(color = Color.White.copy(alpha = .15f))
            Text("全部保存在手机 · 排程 v${state.schedule.version}", color = Color.White.copy(alpha = .8f), style = MaterialTheme.typography.labelSmall)
        } }
        if (!state.preferences.enabled) item { Panel(color = Color(0xFFE4EFE3)) {
            Text("从一条群通知开始", fontWeight = FontWeight.Bold)
            Text("添加微信或 QQ 群白名单，再开启系统通知访问。也可以先手动粘贴通知。", style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = openSettings) { Text("设置通知来源 →") }
        } }
        if (pending > 0) item { FilledTonalButton(onClick = openInbox, modifier = Modifier.fillMaxWidth()) { Text("$pending 条识别结果，等待你确认 →") } }
        items(IntelligenceEngine.risks(state, now)) { RiskPanel(it) }
        item { Panel(color = Color(0xFFE4EFE3)) {
            Text("AI 学习助手", fontWeight = FontWeight.Bold)
            if (!state.preferences.aiEnabled) {
                Text("在设置中配置 DeepSeek 后，可生成今日摘要、风险预测和每周复盘。", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = openSettings) { Text("配置 DeepSeek →") }
            } else {
                LazyRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(AiReportType.entries) { type -> AssistChip(onClick = { onReport(type) }, enabled = !busy, label = { Text(type.label) }) }
                }
                state.aiReports.take(3).forEach { report -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("${report.type.label} · ${report.title}", fontWeight = FontWeight.Medium)
                    Text(report.summary, style = MaterialTheme.typography.bodySmall)
                    report.bullets.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall, color = Muted) }
                } }
            }
        } }
        item { Text("今天的时间线", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold) }
        if (rows.isEmpty()) item { EmptyPanel("今天还没有安排", "新建任务或确认通知后，会在可用时间内自动安排。") }
        items(rows) { row -> Timeline(row, state.preferences.zone) }
        val expired = rows.count { it.block != null && it.end <= now && state.tasks.any { t -> t.id == it.block.taskId && t.status == TaskStatus.ACTIVE } }
        if (expired > 0) item { Text("已过去的时间不会自动算作完成，请在任务中标记完成或修改剩余耗时。", color = Muted, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable private fun InboxPage(state: LocalState, busy: Boolean, onReview: (Notice) -> Unit, onIgnore: (Notice) -> Unit, onReanalyze: (Notice) -> Unit) {
    var onlyReview by rememberSaveable { mutableStateOf(true) }
    val notices = state.notices.filter { !onlyReview || it.status == NoticeStatus.REVIEW }
    LazyColumn(contentPadding = pagePadding, verticalArrangement = gaps) {
        item { PageHeading("MESSAGE → PLAN", "发现，值得行动的信息。",
            when {
                state.preferences.aiEnabled -> "DeepSeek 辅助理解；结果必须由你核对。"
                state.preferences.canvasEnabled -> "群聊由本地规则提取；Canvas 从学校官方 API 同步。"
                else -> "本地规则提取，不联网、不上传群聊内容。"
            }) }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(onlyReview, { onlyReview = true }, label = { Text("待确认") })
            FilterChip(!onlyReview, { onlyReview = false }, label = { Text("全部通知") })
        } }
        if (notices.isEmpty()) item { EmptyPanel(if (onlyReview) "没有待确认的信息" else "还没有收到通知", "可点击下方「录入通知」测试识别，或在设置中开启群通知与 Canvas 同步。") }
        items(notices, key = { it.id }) { n -> Panel {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(when (n.input.source) {
                    Source.MANUAL -> Icons.Outlined.ContentPaste
                    Source.CANVAS -> Icons.Outlined.CloudDownload
                    else -> Icons.Outlined.ChatBubbleOutline
                }, null, tint = Teal)
                Spacer(Modifier.width(8.dp)); Text("${n.input.source.label} · ${n.input.group.ifBlank { "手动录入" }}", Modifier.weight(1f), fontWeight = FontWeight.Bold)
                Text(when (n.status) { NoticeStatus.REVIEW -> "待确认"; NoticeStatus.APPLIED -> "已应用"; NoticeStatus.IGNORED -> "已忽略" }, style = MaterialTheme.typography.labelSmall, color = Teal)
            }
            Text(n.input.content, lineHeight = 24.sp)
            Text("${n.proposal.action.label} · ${n.proposal.title}", color = Teal, fontWeight = FontWeight.Medium)
            n.proposal.uncertainty?.let { uncertainty ->
                Text("本地校验置信度 ${(uncertainty.overall * 100).toInt()}% · 重要性 ${n.proposal.importance}/5",
                    style = MaterialTheme.typography.bodySmall, color = Teal)
                if (uncertainty.blockingFields.isNotEmpty()) Text("需要确认：${uncertainty.blockingFields.joinToString("、")}",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
            }
            if (n.proposal.changeSummary.isNotBlank()) Text(n.proposal.changeSummary, style = MaterialTheme.typography.bodySmall)
            n.proposal.deadline?.let { Text("截止：${formatTime(it, state.preferences.zone)}", style = MaterialTheme.typography.bodySmall) }
            n.proposal.start?.let { Text("日程：${formatTime(it, state.preferences.zone)} — ${formatTime(n.proposal.end, state.preferences.zone)}", style = MaterialTheme.typography.bodySmall) }
            n.proposal.reasons.forEach { Text(it, color = Muted, style = MaterialTheme.typography.bodySmall) }
            n.proposal.evidence.forEach { Text("依据：“$it”", color = Muted, style = MaterialTheme.typography.bodySmall) }
            Text(formatTime(n.input.receivedAt, state.preferences.zone), color = Muted, style = MaterialTheme.typography.labelSmall)
            if (n.status == NoticeStatus.REVIEW) {
                if (state.preferences.aiEnabled && !n.proposal.aiGenerated) TextButton(onClick = { onReanalyze(n) }, enabled = !busy) { Text("用 AI 重新分析") }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = { onIgnore(n) }, enabled = !busy, modifier = Modifier.weight(1f)) { Text("忽略") }
                    Button(onClick = { onReview(n) }, enabled = !busy, modifier = Modifier.weight(1f)) { Text("核对并确认") }
                }
            }
        } }
    }
}

@Composable private fun TasksPage(state: LocalState, busy: Boolean, onEdit: (Task) -> Unit, onComplete: (Task) -> Unit, onCancel: (Task) -> Unit, onSources: (Task) -> Unit, onToggleSubTask: (Task, SubTask) -> Unit) {
    var showHistory by rememberSaveable { mutableStateOf(false) }
    val tasks = state.tasks.filter { showHistory || it.status == TaskStatus.ACTIVE }.sortedWith(compareBy<Task> { it.status != TaskStatus.ACTIVE }.thenBy { it.deadline ?: Instant.MAX })
    LazyColumn(contentPadding = pagePadding, verticalArrangement = gaps) {
        item { PageHeading("SMALL STEPS, REAL PROGRESS", "任务，心中有数。", "剩余耗时会用于排程；完成后请手动打勾。") }
        item { FilterChip(showHistory, { showHistory = !showHistory }, label = { Text("显示已完成 / 已取消") }) }
        if (tasks.isEmpty()) item { EmptyPanel("从第一件事开始", "写下任务、预计耗时和截止时间。") }
        items(tasks, key = { it.id }) { task -> Panel {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { onComplete(task) }, enabled = !busy && task.status == TaskStatus.ACTIVE) { Icon(if (task.status == TaskStatus.ACTIVE) Icons.Outlined.RadioButtonUnchecked else Icons.Outlined.CheckCircle, "标记完成", tint = Teal) }
                Text(task.title, Modifier.weight(1f), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            }
            Text("${task.group.ifBlank { "个人任务" }} · 剩余 ${task.remaining} 分钟", color = Muted, style = MaterialTheme.typography.bodySmall)
            Text("${PersonalTimeModel.resolvedCategory(task).label} · 难度 ${task.difficulty}/5", color = Muted, style = MaterialTheme.typography.bodySmall)
            IntelligenceEngine.personalDurationSuggestion(task, state)?.let { insight ->
                if (insight.sampleCount > 0) Text("个人耗时模型：历史倍率 %.1f，建议约 ${insight.minutes} 分钟".format(insight.multiplier),
                    color = Teal, style = MaterialTheme.typography.bodySmall)
            }
            PersonalTimeModel.bestWindow(task, state)?.let { insight -> Text(
                "较适合：${insight.label} · 历史完成倾向 ${(insight.successRate * 100).toInt()}%（${insight.sampleCount}次）",
                color = Teal, style = MaterialTheme.typography.bodySmall)
            }
            Text("截止 ${formatTime(task.deadline, state.preferences.zone)}${if (task.deadlineLocked) " · 已锁定" else ""}", color = Teal, style = MaterialTheme.typography.bodySmall)
            task.subTasks.forEach { sub -> Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(sub.done, { onToggleSubTask(task, sub) }, enabled = !busy && task.status == TaskStatus.ACTIVE)
                Text(sub.title, style = MaterialTheme.typography.bodySmall)
            } }
            task.actualMinutes?.let { Text("实际用时 $it 分钟", style = MaterialTheme.typography.bodySmall, color = Muted) }
            Row {
                if (task.status == TaskStatus.ACTIVE) { TextButton(onClick = { onEdit(task) }, enabled = !busy) { Text("编辑") }; TextButton(onClick = { onCancel(task) }, enabled = !busy) { Text("取消任务") } }
                else { Text(if (task.status == TaskStatus.COMPLETED) "已完成" else "已取消", modifier = Modifier.padding(12.dp)); TextButton(onClick = { onEdit(task) }, enabled = !busy) { Text("记录实际用时") } }
                TextButton(onClick = { onSources(task) }) { Text("来源") }
            }
        } }
    }
}

@Composable private fun CalendarPage(state: LocalState, day: LocalDate, offset: Int, select: (Int) -> Unit, busy: Boolean,
    onLock: (Block) -> Unit, onOutcome: (Block, ExecutionOutcome) -> Unit,
    onEditEvent: (FixedEvent) -> Unit, onCancelEvent: (FixedEvent) -> Unit) {
    val rows = entries(state, day)
    LazyColumn(contentPadding = pagePadding, verticalArrangement = gaps) {
        item { PageHeading("MAKE TIME FOR WHAT MATTERS", "日历，有条不紊。", "先安排临近截止的任务，再考虑优先级。") }
        item { LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(14) { index ->
            val date = day.minusDays(offset.toLong()).plusDays(index.toLong())
            FilterChip(selected = index == offset, onClick = { select(index) }, label = { Column(Modifier.padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) { Text(if (index == 0) "今天" else date.dayOfWeek.getDisplayName(java.time.format.TextStyle.SHORT, java.util.Locale.CHINA), fontSize = 11.sp); Text(date.dayOfMonth.toString(), fontSize = 22.sp, fontWeight = FontWeight.Bold) } })
        } } }
        items(state.schedule.risks) { RiskPanel(it) }
        item { Text("${day.monthValue}月${day.dayOfMonth}日 · 排程 v${state.schedule.version}", fontWeight = FontWeight.Bold) }
        if (rows.isEmpty()) item { EmptyPanel("这一天，留有余地", "没有固定日程或已分配的任务时间。") }
        items(rows) { row -> Timeline(row, state.preferences.zone) {
            row.block?.let { block -> Column {
                TextButton(onClick = { onLock(block) }, enabled = !busy) { Icon(if (block.locked) Icons.Outlined.LockOpen else Icons.Outlined.Lock, null, modifier = Modifier.size(16.dp)); Spacer(Modifier.width(6.dp)); Text(if (block.locked) "解锁时间" else "锁定时间") }
                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    TextButton(onClick = { onOutcome(block, ExecutionOutcome.COMPLETED) }, enabled = !busy) { Text("完成时段") }
                    TextButton(onClick = { onOutcome(block, ExecutionOutcome.SKIPPED) }, enabled = !busy) { Text("跳过") }
                    TextButton(onClick = { onOutcome(block, ExecutionOutcome.DELAYED) }, enabled = !busy) { Text("延后") }
                }
            } }
            row.event?.let { event -> Row { TextButton(onClick = { onEditEvent(event) }, enabled = !busy) { Text("编辑日程") }; TextButton(onClick = { onCancelEvent(event) }, enabled = !busy) { Text("取消日程") } } }
        } }
        item { Text("排程范围：未来14天，每天 ${state.preferences.startHour}:00–${state.preferences.endHour}:00。时间不足会显示缺口，不会安排到截止之后。", color = Muted, style = MaterialTheme.typography.bodySmall) }
    }
}
