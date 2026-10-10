package com.chronoflow.local.domain

import kotlin.math.round

/** Local verification layer. Model confidence is an input signal, never the final decision. */
object UncertaintyEngine {
    fun assess(input: Incoming, proposal: Proposal, state: LocalState, baseline: Proposal = LocalParser.parse(input, state)): Proposal {
        val needsTarget = proposal.action.name.startsWith("UPDATE") || proposal.action.name.startsWith("CANCEL")
        val isEvent = proposal.action.name.endsWith("EVENT")
        val validTarget = when {
            !needsTarget -> true
            isEvent -> state.events.any { it.id == proposal.targetId }
            else -> state.tasks.any { it.id == proposal.targetId && it.status == TaskStatus.ACTIVE }
        }
        val ambiguityNotes = (proposal.reasons + proposal.questions).joinToString(" ")

        val action = when {
            proposal.action == baseline.action -> 0.94
            proposal.action == Action.IGNORE || baseline.action == Action.IGNORE -> 0.45
            proposal.action.name.removePrefix("CREATE_").removePrefix("UPDATE_").removePrefix("CANCEL_") ==
                baseline.action.name.removePrefix("CREATE_").removePrefix("UPDATE_").removePrefix("CANCEL_") -> 0.62
            else -> 0.35
        }
        val title = when {
            proposal.action == Action.IGNORE -> 1.0
            proposal.title.isBlank() || proposal.title == "待确认事项" -> 0.2
            input.content.replace(" ", "").contains(proposal.title.replace(" ", "")) -> 0.96
            proposal.targetId != null -> 0.88
            else -> 0.72
        }
        val time = when {
            proposal.action == Action.IGNORE || proposal.action.name.startsWith("CANCEL") -> 1.0
            isEvent && proposal.start == null -> 0.15
            isEvent && proposal.end == null -> 0.4
            isEvent && Regex("未说明上午|缺少|无效|多个日期|已过去|跨天").containsMatchIn(ambiguityNotes) -> 0.58
            isEvent -> 0.94
            proposal.deadline == null && proposal.action == Action.UPDATE_TASK -> 0.72
            proposal.deadline == null -> 0.2
            Regex("仅有日期|未说明上午|无效|多个日期|已过去").containsMatchIn(ambiguityNotes) -> 0.62
            else -> 0.94
        }
        val target = when {
            !needsTarget -> 0.96
            !validTarget -> 0.1
            proposal.targetId == baseline.targetId -> 0.96
            else -> 0.78
        }
        val evidence = when {
            !proposal.aiGenerated -> 0.9
            proposal.evidence.isEmpty() -> 0.35
            proposal.evidence.all { input.content.contains(it) } -> (0.74 + proposal.evidence.size * 0.06).coerceAtMost(0.94)
            else -> 0.3
        }
        val fields = FieldConfidence(action.rounded(), title.rounded(), time.rounded(), target.rounded(), evidence.rounded())
        val blocking = buildList {
            if (action < 0.65) add("动作")
            if (title < 0.65) add("事项名称")
            if (time < 0.7) add(if (isEvent) "日程时间" else "截止时间")
            if (target < 0.7) add("目标事项")
            if (proposal.aiGenerated && evidence < 0.55) add("原文证据")
        }
        val questions = buildList {
            if ("动作" in blocking) add("这是新建事项、修改已有事项，还是取消事项？")
            if ("目标事项" in blocking) add("请选择这条通知要修改或取消的已有${if (isEvent) "日程" else "任务"}。")
            if ("日程时间" in blocking) add(if (proposal.start == null) "具体哪天几点开始？预计几点结束？" else "预计几点结束？")
            if ("截止时间" in blocking) add("明确的截止日期和时间是什么？")
            if ("事项名称" in blocking) add("这个任务或日程的准确名称是什么？")
            if ("原文证据" in blocking) add("AI没有找到可核对的原文依据，请确认识别结果是否正确。")
        }.distinct().take(2)
        val overall = (action * .25 + title * .15 + time * .25 + target * .2 + evidence * .15).rounded()
        val create = proposal.action == Action.CREATE_TASK || proposal.action == Action.CREATE_EVENT
        val mayAuto = create && blocking.isEmpty() && overall >= .82 && proposal.inferredFields.isEmpty() &&
            (!proposal.aiGenerated || (proposal.confidence ?: 0.0) >= .85)
        val assessment = UncertaintyAssessment(fields, overall, blocking, questions, mayAuto)
        return proposal.copy(
            reasons = (proposal.reasons + questions).distinct(),
            questions = questions,
            autoSafe = mayAuto,
            confidence = overall,
            uncertainty = assessment,
        )
    }

    private fun Double.rounded(): Double = round(coerceIn(0.0, 1.0) * 100.0) / 100.0
}
