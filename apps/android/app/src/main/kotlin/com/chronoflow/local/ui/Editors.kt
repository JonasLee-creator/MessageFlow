package com.chronoflow.local.ui

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.chronoflow.local.domain.*
import java.time.*
import java.time.format.DateTimeFormatter

fun formatTime(time: Instant?, zone: String, short: Boolean = false): String = time?.atZone(ZoneId.of(zone))?.format(DateTimeFormatter.ofPattern(if (short) "HH:mm" else "M月d日 HH:mm")) ?: "未设置"

@Composable fun TimeField(label: String, value: Instant?, zone: String, onChange: (Instant?) -> Unit, clearable: Boolean = false) {
    val context = LocalContext.current
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        TextButton(onClick = {
            val initial = (value ?: Instant.now()).atZone(ZoneId.of(zone))
            DatePickerDialog(context, { _, year, month, day ->
                TimePickerDialog(context, { _, hour, minute -> onChange(LocalDate.of(year, month + 1, day).atTime(hour, minute).atZone(ZoneId.of(zone)).toInstant()) }, initial.hour, initial.minute, true).show()
            }, initial.year, initial.monthValue - 1, initial.dayOfMonth).show()
        }) { Text("$label\n${formatTime(value, zone)}") }
        if (clearable && value != null) TextButton(onClick = { onChange(null) }) { Text("清除") }
    }
}

@Composable fun TaskEditor(task: Task?, state: LocalState, onDismiss: () -> Unit, onSave: (Task) -> Unit) {
    val zone = state.preferences.zone
    var title by rememberSaveable { mutableStateOf(task?.title.orEmpty()) }
    var group by rememberSaveable { mutableStateOf(task?.group.orEmpty()) }
    var minutes by rememberSaveable { mutableStateOf((task?.minutes ?: 60).toString()) }
    var remaining by rememberSaveable { mutableStateOf((task?.remaining ?: 60).toString()) }
    var dueText by rememberSaveable { mutableStateOf(task?.deadline?.toString()) }
    var split by rememberSaveable { mutableStateOf(task?.splittable ?: true) }
    var locked by rememberSaveable { mutableStateOf(task?.deadlineLocked ?: false) }
    var actual by rememberSaveable { mutableStateOf(task?.actualMinutes?.toString().orEmpty()) }
    var categoryName by rememberSaveable { mutableStateOf((task?.category ?: TaskCategory.AUTO).name) }
    var difficulty by rememberSaveable { mutableStateOf((task?.difficulty ?: 3).toString()) }
    var subTasks by rememberSaveable { mutableStateOf(task?.subTasks?.joinToString("\n") { it.title }.orEmpty()) }
    var error by remember { mutableStateOf<String?>(null) }
    var categoryMenu by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(if (task == null) "新建任务" else "编辑任务") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(title, { title = it }, label = { Text("任务名称") }, singleLine = true)
            OutlinedTextField(group, { group = it }, label = { Text("课程 / 分组") }, singleLine = true)
            Box {
                OutlinedButton(onClick = { categoryMenu = true }, modifier = Modifier.fillMaxWidth()) {
                    Text("任务类型：${TaskCategory.valueOf(categoryName).label}")
                }
                DropdownMenu(categoryMenu, { categoryMenu = false }) {
                    TaskCategory.entries.forEach { category -> DropdownMenuItem(text = { Text(category.label) }, onClick = {
                        categoryName = category.name; categoryMenu = false
                    }) }
                }
            }
            OutlinedTextField(difficulty, { difficulty = it }, label = { Text("难度（1–5）") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true)
            OutlinedTextField(minutes, { minutes = it }, label = { Text("预计总耗时（分钟）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            PersonalTimeModel.durationSuggestion(title, group, TaskCategory.valueOf(categoryName), difficulty.toIntOrNull() ?: 3,
                minutes.toIntOrNull() ?: 60, state)?.let { suggested ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("根据${suggested.basis}（${suggested.sampleCount}个样本），历史倍率 %.1f，建议约 ${suggested.minutes} 分钟".format(suggested.multiplier),
                        style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    TextButton(onClick = { minutes = suggested.minutes.toString(); if (task == null) remaining = suggested.minutes.toString() }) { Text("采用") }
                }
            }
            if (task != null) OutlinedTextField(remaining, { remaining = it }, label = { Text("剩余耗时（分钟）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            OutlinedTextField(subTasks, { subTasks = it }, label = { Text("子任务（每行一项，最多8项）") }, minLines = 3, maxLines = 8)
            if (task != null) OutlinedTextField(actual, { actual = it }, label = { Text("实际用时（分钟，可选）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            TimeField("截止时间", dueText?.let(Instant::parse), zone, { dueText = it?.toString() }, true)
            Toggle("允许拆分时段", split) { split = it }
            Toggle("锁定截止时间", locked) { locked = it }
            Text("排程以 30 分钟为单位，不足半小时向上取整。", style = MaterialTheme.typography.bodySmall)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }, confirmButton = { TextButton(onClick = {
        val duration = minutes.toIntOrNull(); val left = if (task == null) duration else remaining.toIntOrNull(); val spent = actual.toIntOrNull()
        val level = difficulty.toIntOrNull()
        val steps = subTasks.lines().map(String::trim).filter(String::isNotBlank).distinct()
        if (title.isBlank() || title.length > 200 || duration == null || duration !in 1..20160 || left == null || left !in 0..20160) { error = "请填写名称和有效耗时"; return@TextButton }
        if (actual.isNotBlank() && (spent == null || spent !in 1..20160)) { error = "实际用时需为1–20160分钟"; return@TextButton }
        if (level == null || level !in 1..5) { error = "难度需为1–5"; return@TextButton }
        if (steps.size > 8 || steps.any { it.length > 120 }) { error = "子任务最多8项，每项不超过120字"; return@TextButton }
        val previous = task?.subTasks.orEmpty().associateBy { it.title }
        onSave((task ?: Task(title = title)).copy(title = title.trim(), group = group.trim(), minutes = duration, remaining = left,
            deadline = dueText?.let(Instant::parse), splittable = split, deadlineLocked = locked, actualMinutes = spent,
            subTasks = steps.map { previous[it] ?: SubTask(title = it) }, category = TaskCategory.valueOf(categoryName),
            difficulty = level, originalEstimateMinutes = task?.originalEstimateMinutes ?: duration))
    }) { Text("保存并排程") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } })
}

@Composable fun EventEditor(event: FixedEvent?, zone: String, onDismiss: () -> Unit, onSave: (FixedEvent) -> Unit) {
    var title by rememberSaveable { mutableStateOf(event?.title.orEmpty()) }
    var startText by rememberSaveable { mutableStateOf(event?.start?.toString()) }
    var endText by rememberSaveable { mutableStateOf(event?.end?.toString()) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(if (event == null) "添加固定日程" else "编辑固定日程") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(title, { title = it }, label = { Text("课程、会议或考试") })
            TimeField("开始", startText?.let(Instant::parse), zone, { startText = it?.toString() })
            TimeField("结束", endText?.let(Instant::parse), zone, { endText = it?.toString() })
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }, confirmButton = { TextButton(onClick = {
        val start = startText?.let(Instant::parse); val end = endText?.let(Instant::parse)
        if (title.isBlank() || title.length > 200 || start == null || end == null || end <= start) { error = "请填写名称及有效起止时间"; return@TextButton }
        onSave((event ?: FixedEvent(title = title, start = start, end = end)).copy(title = title.trim(), start = start, end = end))
    }) { Text("保存") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } })
}

@Composable fun Toggle(title: String, checked: Boolean, enabled: Boolean = true, change: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text(title, modifier = Modifier.weight(1f)); Switch(checked, change, enabled = enabled)
    }
}

@Composable fun MessageEditor(aiEnabled: Boolean, onDismiss: () -> Unit, onSave: (Incoming) -> Unit) {
    var content by rememberSaveable { mutableStateOf("") }
    var group by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("粘贴群通知") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(group, { group = it }, label = { Text("群名（用于关联已有事项）") })
            OutlinedTextField(content, { content = it }, label = { Text("通知内容") }, minLines = 4, maxLines = 8, placeholder = { Text("实验三明天18:00前提交，预计2小时") })
            Text(if (aiEnabled) "将发送到所选 AI 接口分析，结果仍需你确认。" else "使用本机规则识别，不会发送到服务器。", style = MaterialTheme.typography.bodySmall)
            if (error) Text("请填写 1–10000 字的通知", color = MaterialTheme.colorScheme.error)
        }
    }, confirmButton = { TextButton(onClick = {
        if (content.isBlank() || content.length > 10000) { error = true; return@TextButton }
        onSave(Incoming(Source.MANUAL, group.trim(), content.trim(), Instant.now()))
    }) { Text("识别") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun ReviewEditor(notice: Notice, state: LocalState, onDismiss: () -> Unit, onSave: (Proposal) -> Unit) {
    val original = notice.proposal
    var actionName by rememberSaveable { mutableStateOf(original.action.name) }
    val action = Action.valueOf(actionName)
    var title by rememberSaveable { mutableStateOf(original.title) }
    var target by rememberSaveable { mutableStateOf(original.targetId) }
    var dueText by rememberSaveable { mutableStateOf(original.deadline?.toString()) }
    var startText by rememberSaveable { mutableStateOf(original.start?.toString()) }
    var endText by rememberSaveable { mutableStateOf(original.end?.toString()) }
    var minutes by rememberSaveable { mutableStateOf(original.minutes?.toString().orEmpty()) }
    var error by remember { mutableStateOf<String?>(null) }
    var actionMenu by remember { mutableStateOf(false) }
    var targetMenu by remember { mutableStateOf(false) }
    val isEvent = action.name.endsWith("EVENT")
    val needTarget = action.name.startsWith("UPDATE") || action.name.startsWith("CANCEL")
    val cancelled = action.name.startsWith("CANCEL") || action == Action.IGNORE
    val targets = if (isEvent) state.events.map { it.id to "${it.title} · ${it.group}" } else state.tasks.filter { it.status == TaskStatus.ACTIVE }.map { it.id to "${it.title} · ${it.group}" }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("核对后加入计划") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(notice.input.content, style = MaterialTheme.typography.bodySmall, color = Muted)
            Box {
                OutlinedButton(onClick = { actionMenu = true }, modifier = Modifier.fillMaxWidth()) { Text("动作：${action.label}") }
                DropdownMenu(actionMenu, { actionMenu = false }) { Action.entries.forEach { a -> DropdownMenuItem(text = { Text(a.label) }, onClick = { actionName = a.name; target = null; actionMenu = false }) } }
            }
            if (needTarget) Box {
                OutlinedButton(onClick = { targetMenu = true }) { Text(targets.firstOrNull { it.first == target }?.second ?: "选择对应的已有事项") }
                DropdownMenu(targetMenu, { targetMenu = false }) {
                    targets.forEach { (id, label) -> DropdownMenuItem(text = { Text(label) }, onClick = {
                        target = id; targetMenu = false
                        if (isEvent) state.events.firstOrNull { it.id == id }?.let { event ->
                            title = event.title
                            if (startText == null) startText = event.start.toString()
                            if (endText == null) endText = event.end.toString()
                        }
                    }) }
                    if (targets.isEmpty()) DropdownMenuItem(text = { Text("暂无可选事项，可改为新建") }, onClick = { targetMenu = false })
                }
            }
            if (!cancelled) {
                if (!needTarget || isEvent) OutlinedTextField(title, { title = it }, label = { Text("名称") })
                if (isEvent) {
                    TimeField("开始", startText?.let(Instant::parse), state.preferences.zone, { startText = it?.toString() })
                    TimeField("结束", endText?.let(Instant::parse), state.preferences.zone, { endText = it?.toString() })
                } else {
                    TimeField(if (needTarget && dueText == null) "截止（不修改）" else "截止", dueText?.let(Instant::parse), state.preferences.zone, { dueText = it?.toString() })
                    OutlinedTextField(minutes, { minutes = it }, label = { Text(if (needTarget) "新预计耗时（空白保持原值）" else "预计耗时（空白默认60分钟）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                }
            }
            original.reasons.forEach { Text("• $it", color = MaterialTheme.colorScheme.secondary, style = MaterialTheme.typography.bodySmall) }
            if (original.evidence.isNotEmpty()) {
                Text("原文依据", fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                original.evidence.forEach { Text("“$it”", style = MaterialTheme.typography.bodySmall) }
            }
            if (original.inferredFields.isNotEmpty()) Text("AI 推测字段：${original.inferredFields.joinToString("、")}", color = MaterialTheme.colorScheme.secondary, style = MaterialTheme.typography.bodySmall)
            if (original.subTasks.isNotEmpty()) Text("建议拆解：\n${original.subTasks.joinToString("\n") { "• $it" }}", style = MaterialTheme.typography.bodySmall)
            original.uncertainty?.let { uncertainty ->
                val f = uncertainty.fields
                Text("本地字段级校验", fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                Text("动作 ${(f.action * 100).toInt()}% · 名称 ${(f.title * 100).toInt()}% · 时间 ${(f.time * 100).toInt()}% · 目标 ${(f.target * 100).toInt()}% · 证据 ${(f.evidence * 100).toInt()}%",
                    style = MaterialTheme.typography.bodySmall)
                Text("综合 ${(uncertainty.overall * 100).toInt()}%${if (uncertainty.mayAutoCreate && !original.aiGenerated) " · 满足规则自动创建阈值" else " · 需要人工核对"}",
                    color = if (uncertainty.mayAutoCreate) Teal else MaterialTheme.colorScheme.secondary,
                    style = MaterialTheme.typography.bodySmall)
                uncertainty.questions.forEach { Text("待确认：$it", style = MaterialTheme.typography.bodySmall) }
            }
            Text(if (original.aiGenerated) "AI 辅助识别，确认后才会写入计划。" else "本地规则识别，确认后自动排程。", style = MaterialTheme.typography.bodySmall)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }, confirmButton = { TextButton(onClick = {
        if (needTarget && targets.none { it.first == target }) { error = "请选择已有事项"; return@TextButton }
        val start = startText?.let(Instant::parse); val end = endText?.let(Instant::parse)
        if (!cancelled && ((!needTarget || isEvent) && (title.isBlank() || title.length > 200))) { error = "请填写有效名称"; return@TextButton }
        if (!cancelled && isEvent && (start == null || end == null || end <= start)) { error = "请补充有效的开始和结束时间"; return@TextButton }
        val duration = minutes.toIntOrNull()
        if (!cancelled && !isEvent && minutes.isNotBlank() && (duration == null || duration !in 1..20160)) { error = "耗时需为1–20160分钟"; return@TextButton }
        onSave(original.copy(action = action, title = title.trim(), targetId = target, deadline = dueText?.let(Instant::parse), start = start, end = end, minutes = duration, autoSafe = false))
    }) { Text("确认应用") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("返回") } })
}
