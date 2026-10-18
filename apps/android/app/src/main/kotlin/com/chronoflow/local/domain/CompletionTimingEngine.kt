package com.chronoflow.local.domain

import java.time.Duration
import java.time.Instant
import kotlin.math.ceil
import kotlin.math.roundToLong

data class CompletionTiming(
    val taskId: String,
    val releaseToCompletionMinutes: Long,
    val nonExecutionGapMinutes: Long?,
    val deadlineWindowUsage: Double?,
    val onTime: Boolean?,
    val estimateMultiple: Double,
)

data class CategoryCompletionTiming(
    val category: TaskCategory,
    val sampleCount: Int,
    val medianMinutes: Long,
    val p80Minutes: Long,
)

data class CompletionTimingSummary(
    val sampleCount: Int,
    val medianMinutes: Long,
    val p80Minutes: Long,
    val within24HoursRate: Double,
    val onTimeRate: Double?,
    val medianDeadlineWindowUsage: Double?,
    val categories: List<CategoryCompletionTiming>,
)

/** Measures response efficiency separately from time actually spent doing the work. */
object CompletionTimingEngine {
    fun timing(task: Task): CompletionTiming? {
        if (task.status != TaskStatus.COMPLETED) return null
        val released = task.releasedAt ?: return null
        val completed = task.completedAt ?: return null
        if (completed < released) return null
        val lead = Duration.between(released, completed).toMinutes().coerceAtLeast(0)
        val deadline = task.deadline
        val window = deadline?.let { Duration.between(released, it).toMinutes() }?.takeIf { it > 0 }
        val usage = window?.let { lead.toDouble() / it }
        return CompletionTiming(
            taskId = task.id,
            releaseToCompletionMinutes = lead,
            nonExecutionGapMinutes = task.actualMinutes?.let { (lead - it).coerceAtLeast(0) },
            deadlineWindowUsage = usage,
            onTime = deadline?.let { completed <= it },
            estimateMultiple = lead.toDouble() / task.originalEstimateMinutes.coerceAtLeast(1),
        )
    }

    fun activeAgeMinutes(task: Task, now: Instant): Long? {
        if (task.status != TaskStatus.ACTIVE) return null
        val released = task.releasedAt ?: return null
        if (now < released) return null
        return Duration.between(released, now).toMinutes().coerceAtLeast(0)
    }

    fun summary(tasks: List<Task>): CompletionTimingSummary? {
        val rows = tasks.mapNotNull { task -> timing(task)?.let { task to it } }
        if (rows.isEmpty()) return null
        val leads = rows.map { it.second.releaseToCompletionMinutes }
        val deadlineRows = rows.mapNotNull { it.second.deadlineWindowUsage }
        val onTimeRows = rows.mapNotNull { it.second.onTime }
        val categories = rows.groupBy { PersonalTimeModel.resolvedCategory(it.first) }.map { (category, group) ->
            val values = group.map { it.second.releaseToCompletionMinutes }
            CategoryCompletionTiming(category, values.size, percentile(values, .5), percentile(values, .8))
        }.sortedWith(compareByDescending<CategoryCompletionTiming> { it.sampleCount }.thenBy { it.category.label })
        return CompletionTimingSummary(
            sampleCount = rows.size,
            medianMinutes = percentile(leads, .5),
            p80Minutes = percentile(leads, .8),
            within24HoursRate = leads.count { it <= 24 * 60 }.toDouble() / leads.size,
            onTimeRate = onTimeRows.takeIf { it.isNotEmpty() }?.let { values -> values.count { it }.toDouble() / values.size },
            medianDeadlineWindowUsage = deadlineRows.takeIf { it.isNotEmpty() }?.let { percentileDouble(it, .5) },
            categories = categories,
        )
    }

    private fun percentile(values: List<Long>, quantile: Double): Long {
        val sorted = values.sorted()
        val position = quantile.coerceIn(0.0, 1.0) * sorted.lastIndex
        val lower = position.toInt()
        val upper = ceil(position).toInt()
        if (lower == upper) return sorted[lower]
        return (sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)).roundToLong()
    }

    private fun percentileDouble(values: List<Double>, quantile: Double): Double {
        val sorted = values.sorted()
        val position = quantile.coerceIn(0.0, 1.0) * sorted.lastIndex
        val lower = position.toInt()
        val upper = ceil(position).toInt()
        if (lower == upper) return sorted[lower]
        return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)
    }
}
