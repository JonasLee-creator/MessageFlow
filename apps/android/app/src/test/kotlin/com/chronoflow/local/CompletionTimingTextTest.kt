package com.chronoflow.local

import com.chronoflow.local.domain.CompletionTimingEngine
import com.chronoflow.local.domain.Task
import com.chronoflow.local.domain.TaskStatus
import com.chronoflow.local.ui.formatDeadlineWindowUsage
import java.time.Instant
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class CompletionTimingTextTest {
    @Test fun completedTaskWithDeadlineCanRenderTodaySummary() {
        val release = Instant.parse("2026-10-18T00:00:00Z")
        val task = Task(
            title = "复习", status = TaskStatus.COMPLETED,
            releasedAt = release, deadline = release.plusSeconds(7200),
            completedAt = release.plusSeconds(3600),
        )
        val usage = CompletionTimingEngine.summary(listOf(task))?.medianDeadlineWindowUsage
        assertNotNull(usage)
        assertEquals("中位截止窗口使用率 50%；超过 100% 表示完成时已逾期。",
            formatDeadlineWindowUsage(requireNotNull(usage), Locale.CHINA))
    }

    @Test fun percentageAndLiteralThresholdRenderWithoutFormatExceptions() {
        for (locale in listOf(Locale.CHINA, Locale.US)) {
            for ((usage, percent) in listOf(0.0 to "0%", 1.0 to "100%", 1.25 to "125%")) {
                assertEquals("中位截止窗口使用率 $percent；超过 100% 表示完成时已逾期。",
                    formatDeadlineWindowUsage(usage, locale))
            }
        }
    }
}
