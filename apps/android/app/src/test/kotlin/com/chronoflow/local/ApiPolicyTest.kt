package com.chronoflow.local

import com.chronoflow.local.domain.*
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ApiPolicyTest {
    @Test fun userEndpointsAndProductionPolicy() {
        assertEquals("https://provider.example/v1/chat/completions", AiApiPolicy.completionUrl("https://provider.example/v1/"))
        assertTrue(runCatching { AiApiPolicy.baseUrl("http://provider.example") }.isFailure)
        assertTrue(runCatching { AiApiPolicy.baseUrl("https://user:secret@provider.example") }.isFailure)
        assertTrue(runCatching { AiApiPolicy.baseUrl("https://provider.example?key=secret") }.isFailure)
        val user = Preferences(aiEnabled = true, deepSeekApiKey = "offline-check-key", deepSeekModel = "offline-model", aiBaseUrl = "https://provider.example/v1")
        AiApiPolicy.validate(user, false)
        val official = user.copy(aiApiMode = ApiMode.OFFICIAL, officialGatewayUrl = "https://chronoflow.example", officialAccessCode = "offline-access-code-123456")
        AiApiPolicy.validate(official, true)
        assertTrue(runCatching { AiApiPolicy.validate(official, false) }.isFailure)
        assertTrue(runCatching { AiApiPolicy.validate(user.copy(deepSeekApiKey = ""), true) }.isFailure)
    }
    @Test fun aiResultsAlwaysRemainForReview() {
        val now = Instant.parse("2026-10-15T00:00:00Z")
        val input = Incoming(Source.MANUAL, "课程", "实验三明天18:00前提交，预计2小时", now)
        val state = LocalState(preferences = Preferences(autoCreate = true, zone = "Asia/Shanghai"))
        val proposal = Proposal(Action.CREATE_TASK, "实验三", deadline = now.plusSeconds(34 * 3600), minutes = 120,
            evidence = listOf("实验三", "明天18:00前提交", "预计2小时"), confidence = .99, aiGenerated = true)
        val next = LocalEngine.ingestAnalyzed(state, input, listOf(proposal), now)
        assertTrue(next.tasks.isEmpty())
        assertEquals(NoticeStatus.REVIEW, next.notices.single().status)
    }
}
