package com.chronoflow.local

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.Rule
import org.junit.Test

class NavigationTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    @Test fun fivePagesOpenWithoutServer() {
        for (tab in listOf("发现", "任务", "日历", "设置", "今天")) {
            rule.onNodeWithText(tab, useUnmergedTree = true).performClick()
            rule.waitForIdle()
        }
        rule.onNodeWithText("把今天，安排从容。").assertIsDisplayed()
    }
}
