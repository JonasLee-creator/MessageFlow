package com.chronoflow.local.ui

import java.util.Locale

internal fun formatDeadlineWindowUsage(usage: Double, locale: Locale = Locale.getDefault()): String {
    // Format only the numeric percentage. Literal percent signs in explanatory
    // text must never be interpreted as Formatter directives during composition.
    val percentage = String.format(locale, "%.0f%%", usage * 100)
    return "中位截止窗口使用率 $percentage；超过 100% 表示完成时已逾期。"
}
