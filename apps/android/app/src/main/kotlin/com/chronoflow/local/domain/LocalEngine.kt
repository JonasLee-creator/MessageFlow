package com.chronoflow.local.domain

import java.time.Duration
import java.time.Instant

/** Pure state transitions: a persisted notice can be applied once only. */
object LocalEngine {
    fun ingest(state: LocalState, input: Incoming, now: Instant): LocalState {
        return ingestAnalyzed(state, input, listOf(LocalParser.parse(input, state)), now)
    }

    fun ingestAnalyzed(state: LocalState, input: Incoming, proposals: List<Proposal>, now: Instant): LocalState {
        require(input.content.isNotBlank() && input.content.length <= 10000)
        val duplicate = state.notices.any { old ->
            old.input.source == input.source && old.input.group == input.group && old.input.sender == input.sender &&
                old.input.content == input.content && (old.input.receivedAt == input.receivedAt ||
                Duration.between(old.input.receivedAt, input.receivedAt).abs() <= Duration.ofMinutes(10))
        }
        if (duplicate) return state
        val baseline = LocalParser.parse(input, state)
        val safe = proposals.ifEmpty { listOf(baseline) }.take(10).map { UncertaintyEngine.assess(input, it, state, baseline) }
        val notices = safe.mapIndexed { index, proposal ->
            Notice(input = input.copy(sourceKey = input.sourceKey + if (safe.size > 1) "#${index + 1}" else ""), proposal = proposal,
                status = if (proposal.action == Action.IGNORE) NoticeStatus.IGNORED else NoticeStatus.REVIEW)
        }
        var next = state.copy(notices = (notices + state.notices).take(1000))
        notices.filter { state.preferences.autoCreate && it.proposal.autoSafe }.forEach { notice -> next = apply(next, notice.id, notice.proposal, now) }
        return next
    }

    fun apply(state: LocalState, noticeId: String, proposal: Proposal, now: Instant): LocalState {
        val notice = state.notices.firstOrNull { it.id == noticeId } ?: error("通知不存在")
        require(notice.status == NoticeStatus.REVIEW) { "通知已经处理" }
        var tasks = state.tasks
        var events = state.events
        var appliedId: String? = null
        when (proposal.action) {
            Action.IGNORE -> Unit
            Action.CREATE_TASK -> {
                validateTitle(proposal.title)
                val minutes = proposal.minutes ?: 60
                require(minutes in 1..20160) { "耗时必须在 1–20160 分钟之间" }
                val task = Task(title = proposal.title, group = notice.input.group, source = notice.input.source, deadline = proposal.deadline, minutes = minutes, sourceIds = listOf(notice.id))
                    .copy(subTasks = proposal.subTasks.map { SubTask(title = it) })
                tasks = tasks + task; appliedId = task.id
            }
            Action.UPDATE_TASK, Action.CANCEL_TASK -> {
                val task = tasks.firstOrNull { it.id == proposal.targetId && it.status == TaskStatus.ACTIVE } ?: error("请选择有效的已有任务")
                proposal.minutes?.let { require(it in 1..20160) { "预计耗时无效" } }
                appliedId = task.id
                tasks = tasks.map { if (it.id != task.id) it else if (proposal.action == Action.CANCEL_TASK) it.copy(status = TaskStatus.CANCELLED, sourceIds = it.sourceIds + notice.id)
                    else it.copy(deadline = if (it.deadlineLocked) it.deadline else proposal.deadline ?: it.deadline,
                        minutes = proposal.minutes ?: it.minutes,
                        remaining = proposal.minutes?.let { minutes -> (minutes - (it.minutes - it.remaining).coerceAtLeast(0)).coerceAtLeast(0) } ?: it.remaining,
                        subTasks = if (proposal.subTasks.isEmpty()) it.subTasks else proposal.subTasks.map { title -> SubTask(title = title) },
                        deadlineChanges = it.deadlineChanges + if (proposal.deadline != null && proposal.deadline != it.deadline) 1 else 0,
                        sourceIds = it.sourceIds + notice.id)
                }
            }
            Action.CREATE_EVENT, Action.UPDATE_EVENT -> {
                validateTitle(proposal.title)
                val start = proposal.start ?: error("请补充日程开始时间")
                val end = proposal.end ?: error("请补充日程结束时间")
                require(end > start) { "结束时间必须晚于开始时间" }
                if (proposal.action == Action.CREATE_EVENT) {
                    val event = FixedEvent(title = proposal.title, start = start, end = end, group = notice.input.group, source = notice.input.source, sourceIds = listOf(notice.id))
                    events = events + event; appliedId = event.id
                } else {
                    val event = events.firstOrNull { it.id == proposal.targetId } ?: error("请选择有效的已有日程")
                    events = events.map { if (it.id != event.id) it else it.copy(title = proposal.title, start = start, end = end, sourceIds = it.sourceIds + notice.id) }
                    appliedId = event.id
                }
            }
            Action.CANCEL_EVENT -> {
                val event = events.firstOrNull { it.id == proposal.targetId } ?: error("请选择有效的已有日程")
                events = events.filterNot { it.id == event.id }; appliedId = event.id
            }
        }
        val next = state.copy(tasks = tasks, events = events, notices = state.notices.map { if (it.id != notice.id) it else it.copy(
            proposal = proposal, status = if (proposal.action == Action.IGNORE) NoticeStatus.IGNORED else NoticeStatus.APPLIED, appliedId = appliedId) })
        return if (proposal.action == Action.IGNORE) next else next.copy(schedule = LocalScheduler.plan(next, now))
    }

    fun saveTask(state: LocalState, task: Task, now: Instant): LocalState {
        validateTitle(task.title)
        require(task.minutes in 1..20160 && task.remaining in 0..20160 && task.priority in 1..10 &&
            task.difficulty in 1..5 && task.originalEstimateMinutes in 1..20160) { "请检查耗时、难度和优先级" }
        val next = state.copy(tasks = state.tasks.filterNot { it.id == task.id } + task)
        return next.copy(schedule = LocalScheduler.plan(next, now))
    }

    fun saveEvent(state: LocalState, event: FixedEvent, now: Instant): LocalState {
        validateTitle(event.title)
        require(event.end > event.start) { "结束时间必须晚于开始时间" }
        val next = state.copy(events = state.events.filterNot { it.id == event.id } + event)
        return next.copy(schedule = LocalScheduler.plan(next, now))
    }
    private fun validateTitle(title: String) { require(title.isNotBlank() && title.length <= 200) { "名称需为 1–200 个字符" } }
}
