package com.chronoflow.local

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.Rule
import org.junit.Test

class NavigationTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    @Test fun fivePagesOpenWithoutServer() {
        rule.waitUntil(10000) {
            rule.onAllNodesWithText("游客模式").fetchSemanticsNodes().isNotEmpty() || rule.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty()
        }
        if (rule.onAllNodesWithText("游客模式").fetchSemanticsNodes().isNotEmpty()) {
            rule.waitUntil(10000) { runCatching { rule.onNodeWithText("游客模式").assertIsEnabled(); true }.getOrDefault(false) }
            rule.onNodeWithText("游客模式").performClick()
            rule.waitUntil(10000) { rule.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty() }
        }
        for (tab in listOf("发现", "任务", "日历", "设置", "今天")) {
            rule.onNodeWithText(tab, useUnmergedTree = true).performClick()
            rule.waitForIdle()
        }
        rule.onNodeWithText("把今天，安排从容。").assertIsDisplayed()
    }
}
