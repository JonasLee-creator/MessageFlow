package com.chronoflow.local

import androidx.test.platform.app.InstrumentationRegistry
import com.chronoflow.local.domain.*
import com.chronoflow.local.model.ModelPlannerClient
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

/** Uses the actual APK weights. Run on a phone/emulator in airplane mode. */
class EmbeddedModelTest {
    @Test fun bundledModelRespectsClasses() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val zone = ZoneId.of("Asia/Shanghai")
        val now = Instant.now()
        val day = now.atZone(zone).toLocalDate().plusDays(1)
        val start = day.atTime(9, 0).atZone(zone).toInstant()
        val end = day.atTime(11, 0).atZone(zone).toInstant()
        val task = Task(id = "embedded-smoke", title = "完成实验报告", minutes = 60, remaining = 60,
            deadline = day.plusDays(1).atTime(22, 0).atZone(zone).toInstant(), releasedAt = now.minusSeconds(86400))
        val state = LocalState(preferences = Preferences(zone = zone.id), tasks = listOf(task),
            events = listOf(FixedEvent(title = "固定课程", start = start, end = end)))
        val plan = ModelPlannerClient(context).plan(state)
        assertEquals("chronoflow-local", plan.engine)
        val forecast = plan.modelPredictions.single()
        assertTrue(forecast.p50Minutes > 0)
        assertTrue(forecast.p50Minutes <= forecast.p80Minutes && forecast.p80Minutes <= forecast.p95Minutes)
        assertTrue(plan.blocks.isNotEmpty())
        assertEquals(60L, plan.blocks.sumOf { java.time.Duration.between(it.start, it.end).toMinutes() })
        assertTrue(plan.blocks.none { LocalScheduler.overlaps(it.start, it.end, start, end) })
        assertTrue(plan.blocks.all { it.taskId == task.id })
    }
}
