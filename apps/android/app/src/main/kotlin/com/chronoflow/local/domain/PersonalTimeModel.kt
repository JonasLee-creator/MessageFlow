package com.chronoflow.local.domain

import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import kotlin.math.roundToInt

data class DurationSuggestion(
    val minutes: Int,
    val multiplier: Double,
    val sampleCount: Int,
    val basis: String,
)

data class TimeWindowInsight(
    val label: String,
    val successRate: Double,
    val sampleCount: Int,
)

/** Explainable, on-device personalization with conservative priors for sparse personal data. */
object PersonalTimeModel {
    private data class RatioSample(val ratio: Double, val category: TaskCategory, val group: String, val difficulty: Int)

    fun inferCategory(title: String): TaskCategory = when {
        Regex("编程|代码|程序|算法|开发|coding|code", RegexOption.IGNORE_CASE).containsMatchIn(title) -> TaskCategory.PROGRAMMING
        Regex("实验|实训|lab", RegexOption.IGNORE_CASE).containsMatchIn(title) -> TaskCategory.EXPERIMENT
        Regex("报告|论文|汇报|文档|report|paper", RegexOption.IGNORE_CASE).containsMatchIn(title) -> TaskCategory.REPORT
        Regex("复习|备考|刷题|考试|review|quiz", RegexOption.IGNORE_CASE).containsMatchIn(title) -> TaskCategory.REVIEW
        Regex("背诵|记忆|单词|默写", RegexOption.IGNORE_CASE).containsMatchIn(title) -> TaskCategory.MEMORIZATION
        Regex("阅读|读书|文献|reading", RegexOption.IGNORE_CASE).containsMatchIn(title) -> TaskCategory.READING
        else -> TaskCategory.OTHER
    }

    fun resolvedCategory(task: Task): TaskCategory =
        if (task.category == TaskCategory.AUTO) inferCategory(task.title) else task.category

    fun durationSuggestion(
        title: String,
        group: String,
        category: TaskCategory,
        difficulty: Int,
        baseMinutes: Int,
        state: LocalState,
    ): DurationSuggestion? {
        val resolved = if (category == TaskCategory.AUTO) inferCategory(title) else category
        val samples = durationSamples(state)
        if (samples.isEmpty()) return null

        val global = posterior(1.0, 4.0, samples.map { it.ratio })
        val categorySamples = samples.filter { it.category == resolved }
        val byCategory = posterior(global, 4.0, categorySamples.map { it.ratio })
        val groupSamples = categorySamples.filter { group.isNotBlank() && it.group == group }
        val byGroup = posterior(byCategory, 3.0, groupSamples.map { it.ratio })
        val difficultySamples = groupSamples.filter { kotlin.math.abs(it.difficulty - difficulty) <= 1 }
        val ratio = posterior(byGroup, 2.0, difficultySamples.map { it.ratio }).coerceIn(0.5, 3.0)
        val count = when {
            difficultySamples.isNotEmpty() -> difficultySamples.size
            groupSamples.isNotEmpty() -> groupSamples.size
            categorySamples.isNotEmpty() -> categorySamples.size
            else -> samples.size
        }
        val basis = when {
            difficultySamples.isNotEmpty() -> "同课程、同类型且难度接近的历史"
            groupSamples.isNotEmpty() -> "同课程、同类型的历史"
            categorySamples.isNotEmpty() -> "${resolved.label}类任务历史"
            else -> "全部已完成任务历史"
        }
        val suggested = (baseMinutes.coerceIn(1, 20160) * ratio / 5.0).roundToInt().times(5).coerceIn(5, 20160)
        return DurationSuggestion(suggested, ratio, count, basis)
    }

    fun slotScore(task: Task, start: Instant, state: LocalState): Double {
        val category = resolvedCategory(task)
        val bucket = bucket(start, state.preferences.zone)
        val matching = state.executionHistory.filter {
            it.category == category && bucket(it.plannedStart, state.preferences.zone) == bucket
        }
        if (matching.isEmpty()) return 0.5
        val successes = matching.sumOf { when (it.outcome) {
            ExecutionOutcome.COMPLETED -> 1.0
            ExecutionOutcome.DELAYED -> 0.25
            ExecutionOutcome.SKIPPED -> 0.0
        } }
        return (successes + 2.0) / (matching.size + 4.0)
    }

    fun bestWindow(task: Task, state: LocalState): TimeWindowInsight? {
        val category = resolvedCategory(task)
        val relevant = state.executionHistory.filter { it.category == category }
        if (relevant.isEmpty()) return null
        return (0..3).mapNotNull { index ->
            val rows = relevant.filter { bucket(it.plannedStart, state.preferences.zone) == index }
            if (rows.isEmpty()) null else {
                val success = rows.sumOf { if (it.outcome == ExecutionOutcome.COMPLETED) 1.0 else 0.0 }
                TimeWindowInsight(bucketLabel(index), (success + 2.0) / (rows.size + 4.0), rows.size)
            }
        }.maxByOrNull { it.successRate }
    }

    fun record(state: LocalState, blockId: String, outcome: ExecutionOutcome, actualMinutes: Int?, now: Instant): LocalState {
        val block = state.schedule.blocks.firstOrNull { it.id == blockId } ?: error("时间块不存在")
        val task = state.tasks.firstOrNull { it.id == block.taskId && it.status == TaskStatus.ACTIVE } ?: error("任务已经结束")
        val planned = Duration.between(block.start, block.end).toMinutes().toInt().coerceAtLeast(1)
        val actual = actualMinutes?.also { require(it in 1..20160) { "实际用时需为1–20160分钟" } }
        val record = ExecutionRecord(taskId = task.id, category = resolvedCategory(task), group = task.group,
            plannedStart = block.start, plannedMinutes = planned, actualMinutes = actual, outcome = outcome, recordedAt = now)
        val credited = if (outcome == ExecutionOutcome.COMPLETED) actual ?: planned else 0
        val nextTasks = state.tasks.map { current ->
            if (current.id != task.id) current else {
                val left = (current.remaining - credited).coerceAtLeast(0)
                val completed = left == 0
                val totalActual = (state.executionHistory.filter { it.taskId == task.id && it.outcome == ExecutionOutcome.COMPLETED }
                    .sumOf { it.actualMinutes ?: it.plannedMinutes } + credited).takeIf { completed }
                current.copy(remaining = left, status = if (completed) TaskStatus.COMPLETED else current.status,
                    actualMinutes = totalActual ?: current.actualMinutes, completedAt = if (completed) now else current.completedAt)
            }
        }
        return state.copy(tasks = nextTasks,
            schedule = state.schedule.copy(blocks = state.schedule.blocks.filterNot { it.id == blockId }),
            executionHistory = (state.executionHistory + record).takeLast(2000))
    }

    private fun durationSamples(state: LocalState): List<RatioSample> {
        val taskRows = state.tasks.mapNotNull { task ->
            val actual = task.actualMinutes ?: return@mapNotNull null
            if (task.status != TaskStatus.COMPLETED || task.originalEstimateMinutes <= 0) return@mapNotNull null
            RatioSample((actual.toDouble() / task.originalEstimateMinutes).coerceIn(0.25, 4.0), resolvedCategory(task), task.group, task.difficulty)
        }
        val sessionRows = state.executionHistory.mapNotNull { record ->
            val actual = record.actualMinutes ?: return@mapNotNull null
            if (record.outcome != ExecutionOutcome.COMPLETED || record.plannedMinutes <= 0) return@mapNotNull null
            val difficulty = state.tasks.firstOrNull { it.id == record.taskId }?.difficulty ?: 3
            RatioSample((actual.toDouble() / record.plannedMinutes).coerceIn(0.25, 4.0), record.category, record.group, difficulty)
        }
        return taskRows + sessionRows
    }

    private fun posterior(priorMean: Double, priorWeight: Double, rows: List<Double>): Double =
        (priorMean * priorWeight + rows.sum()) / (priorWeight + rows.size)

    private fun bucket(instant: Instant, zone: String): Int = when (instant.atZone(ZoneId.of(zone)).hour) {
        in 6..11 -> 0
        in 12..17 -> 1
        in 18..20 -> 2
        else -> 3
    }

    private fun bucketLabel(bucket: Int): String = when (bucket) {
        0 -> "上午 06:00–12:00"
        1 -> "下午 12:00–18:00"
        2 -> "晚间 18:00–21:00"
        else -> "夜间 21:00 后"
    }
}
