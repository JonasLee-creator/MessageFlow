package com.chronoflow.local

import com.chronoflow.local.domain.*
import java.time.*
import kotlin.random.Random

/** Same production domain code, runnable with a preinstalled Kotlin/JDK only. */
object CoreChecks {
    private val clock = Instant.parse("2026-10-04T00:00:00Z") // Sunday, Shanghai 08:00
    private val prefs = Preferences(zone = "Asia/Shanghai")
    private val empty = LocalState(preferences = prefs)
    private fun incoming(text: String, group: String = "网络课", source: Source = Source.WECHAT) = Incoming(source, group, text, clock)
    private fun task(title: String = "实验三", minutes: Int = 60, hours: Long = 8, split: Boolean = true) = Task(title = title, group = "网络课", source = Source.WECHAT,
        deadline = clock.plusSeconds(hours * 3600), minutes = minutes, splittable = split)
    private fun fail(block: () -> Unit) { check(runCatching(block).isFailure) { "Expected validation failure" } }

    @JvmStatic fun main(args: Array<String>) { runAll() }
    fun runAll() {
        var count = 0
        fun test(name: String, body: () -> Unit) { body(); count++; println("PASS $name") }
        test("explicit task deadline and duration are local auto-safe") {
            val p = LocalParser.parse(incoming("实验三明天18:00前提交，预计2小时"), empty)
            check(p.action == Action.CREATE_TASK && p.title == "实验三")
            check(p.deadline == Instant.parse("2026-10-05T10:00:00Z") && p.minutes == 120)
            check(p.autoSafe) { p.toString() }
        }
        test("date-only deadline always needs review") {
            val p = LocalParser.parse(incoming("实验三周五前提交"), empty)
            check(p.deadline == Instant.parse("2026-10-09T15:59:00Z")); check(!p.autoSafe)
        }
        test("Chinese PM event range") {
            val p = LocalParser.parse(incoming("明天下午三点到四点开班会"), empty)
            check(p.action == Action.CREATE_EVENT)
            check(p.start == Instant.parse("2026-10-05T07:00:00Z")) { p.toString() }
            check(p.end == Instant.parse("2026-10-05T08:00:00Z")) { p.toString() }
        }
        test("time range is not misread as month-day") {
            val p = LocalParser.parse(incoming("明天14:00-15:30会议"), empty)
            check(p.start == Instant.parse("2026-10-05T06:00:00Z")); check(p.end == Instant.parse("2026-10-05T07:30:00Z"))
            check(p.autoSafe) { p.toString() }
        }
        test("explicit ISO date") {
            val p = LocalParser.parse(incoming("实验三2026-10-12 18:00提交，预计30分钟"), empty)
            check(p.deadline == Instant.parse("2026-10-12T10:00:00Z")) { p.toString() }
        }
        test("invalid date does not crash or invent deadline") {
            val p = LocalParser.parse(incoming("实验三2026年2月30日提交"), empty)
            check(p.deadline == null && !p.autoSafe)
        }
        test("unknown date stays null") {
            val p = LocalParser.parse(incoming("实验三等老师通知再提交"), empty)
            check(p.deadline == null && !p.autoSafe)
        }
        test("ambiguous Chinese clock hour is never automatic") {
            check(!LocalParser.parse(incoming("明天三点到四点开会"), empty).autoSafe)
        }
        test("truncated notification requires review") {
            check(!LocalParser.parse(incoming("实验三明天18:00提交，预计2小时…"), empty).autoSafe)
        }
        test("invalid clock does not turn into a fabricated deadline") {
            val p = LocalParser.parse(incoming("实验三明天25:99前提交，预计1小时"), empty)
            check(p.deadline == null && !p.autoSafe)
        }
        test("ordinary conversation ignored") { check(LocalParser.parse(incoming("晚上有人吃饭吗"), empty).action == Action.IGNORE) }
        test("postponement takes precedence over no-submit wording") {
            val existing = task()
            val p = LocalParser.parse(incoming("实验三不用周五交了，改到下周一18:00提交"), empty.copy(tasks = listOf(existing)))
            check(p.action == Action.UPDATE_TASK && p.targetId == existing.id)
            check(p.deadline == Instant.parse("2026-10-05T10:00:00Z")); check(!p.autoSafe)
        }
        test("similar lab numbers do not match") {
            val p = LocalParser.parse(incoming("实验三十延期到明天"), empty.copy(tasks = listOf(task("实验三"))))
            check(p.targetId == null)
        }
        test("group matching prevents cross-class mutation") {
            val p = LocalParser.parse(incoming("实验三延期到明天", group = "别的班"), empty.copy(tasks = listOf(task())))
            check(p.targetId == null)
        }
        test("source matching prevents same-name QQ group mutating WeChat") {
            val p = LocalParser.parse(incoming("实验三延期到明天", source = Source.QQ), empty.copy(tasks = listOf(task())))
            check(p.targetId == null)
        }
        test("ambiguous task target requires selection") {
            val p = LocalParser.parse(incoming("实验三延期到明天"), empty.copy(tasks = listOf(task(), task())))
            check(p.targetId == null && !p.autoSafe)
        }
        test("event cancellation finds existing class") {
            val event = FixedEvent(title = "高数", start = clock.plusSeconds(3600), end = clock.plusSeconds(7200), group = "网络课", source = Source.WECHAT)
            val p = LocalParser.parse(incoming("明天高数取消"), empty.copy(events = listOf(event)))
            check(p.action == Action.CANCEL_EVENT && p.targetId == event.id && !p.autoSafe)
        }
        test("missing event end requires review") {
            val p = LocalParser.parse(incoming("明天15:00开会"), empty)
            check(p.start != null && p.end == null && !p.autoSafe)
        }
        test("overnight event not silently inverted") {
            val p = LocalParser.parse(incoming("明天23:00-01:00会议"), empty)
            check(p.end == null && !p.autoSafe)
        }
        val enabled = prefs.copy(enabled = true, groups = listOf(GroupRule(Source.WECHAT, "网络课"), GroupRule(Source.QQ, "QQ课程群")))
        fun envelope(pkg: String = Source.WECHAT.packageName, title: String = "网络课") = NotificationEnvelope(pkg, "key", clock.toEpochMilli(), title = title, text = "实验三明天提交")
        test("WeChat exact whitelist") { check(NotificationMatcher.extract(envelope(), enabled).size == 1) }
        test("QQ unread and sender group title") {
            check(NotificationMatcher.extract(envelope(Source.QQ.packageName, "张老师(QQ课程群)"), enabled).size == 1)
            check(NotificationMatcher.extract(envelope(Source.QQ.packageName, "QQ课程群(2条新消息)"), enabled).size == 1)
        }
        test("disabled and unlisted notifications filtered") {
            check(NotificationMatcher.extract(envelope(), prefs).isEmpty())
            check(NotificationMatcher.extract(envelope(title = "私聊"), enabled).isEmpty())
            check(NotificationMatcher.extract(envelope(title = "网络课程群2"), enabled).isEmpty())
            check(NotificationMatcher.extract(envelope(pkg = "untrusted.app"), enabled).isEmpty())
        }
        test("matching summary accepted; individual MessagingStyle messages preserved") {
            check(NotificationMatcher.extract(envelope().copy(summary = true), enabled).size == 1)
            val rows = NotificationMatcher.extract(envelope().copy(messages = listOf(MessagePart("实验三明天交", "老师", 1000), MessagePart("明天开会", "班长", 2000))), enabled)
            check(rows.size == 2 && rows[0].receivedAt == Instant.ofEpochMilli(1000))
        }
        test("WeChat group can be identified from subtext or body prefix") {
            check(NotificationMatcher.extract(envelope(title = "微信").copy(subText = "网络课"), enabled).size == 1)
            check(NotificationMatcher.extract(envelope(title = "微信").copy(text = "【网络课】：实验三明天提交"), enabled).size == 1)
        }
        test("conversation title wins when sender shown in title") {
            check(NotificationMatcher.extract(envelope(title = "张老师").copy(conversationTitle = "网络课"), enabled).size == 1)
        }
        test("irrelevant group chatter filtered") { check(NotificationMatcher.extract(envelope().copy(text = "晚上吃什么"), enabled).isEmpty()) }
        test("replayed legacy notification deduped for ten minutes") {
            val first = LocalEngine.ingest(empty, incoming("实验三明天提交"), clock)
            val second = LocalEngine.ingest(first, incoming("实验三明天提交").copy(receivedAt = clock.plusSeconds(30)), clock)
            check(second.notices.size == 1)
            val third = LocalEngine.ingest(second, incoming("实验三明天提交").copy(receivedAt = clock.plusSeconds(601)), clock)
            check(third.notices.size == 2)
        }
        test("default ingestion does not change tasks before confirmation") {
            val state = LocalEngine.ingest(empty, incoming("实验三明天18:00提交，预计2小时"), clock)
            check(state.tasks.isEmpty() && state.notices.single().status == NoticeStatus.REVIEW)
        }
        test("Canvas assignment enters review with structured deadline") {
            val item = CanvasItem("assignment:1:9", CanvasItemType.ASSIGNMENT, "机器学习", "实验四", dueAt = clock.plusSeconds(86400))
            val result = CanvasSyncEngine.merge(empty, listOf(item), clock)
            val notice = result.state.notices.single()
            check(result.stats.added == 1 && notice.input.source == Source.CANVAS)
            check(notice.proposal.action == Action.CREATE_TASK && notice.proposal.deadline == item.dueAt && !notice.proposal.autoSafe)
        }
        test("unchanged Canvas records do not create duplicates") {
            val item = CanvasItem("assignment:1:9", CanvasItemType.ASSIGNMENT, "机器学习", "实验四", dueAt = clock.plusSeconds(86400))
            val first = CanvasSyncEngine.merge(empty, listOf(item), clock).state
            val second = CanvasSyncEngine.merge(first, listOf(item.copy(updatedAt = clock.plusSeconds(60))), clock.plusSeconds(60))
            check(second.state.notices.size == 1 && second.stats.unchanged == 1)
        }
        test("Canvas deadline change updates the confirmed task through review") {
            val item = CanvasItem("assignment:1:9", CanvasItemType.ASSIGNMENT, "机器学习", "实验四", dueAt = clock.plusSeconds(86400))
            val imported = CanvasSyncEngine.merge(empty, listOf(item), clock).state
            val notice = imported.notices.single()
            val applied = LocalEngine.apply(imported, notice.id, notice.proposal, clock)
            val changed = CanvasSyncEngine.merge(applied, listOf(item.copy(dueAt = clock.plusSeconds(172800))), clock.plusSeconds(60))
            val update = changed.state.notices.first()
            check(changed.stats.updated == 1 && update.proposal.action == Action.UPDATE_TASK)
            check(update.proposal.targetId == applied.tasks.single().id && update.proposal.deadline == clock.plusSeconds(172800))
        }
        test("pending Canvas update replaces its earlier review card") {
            val item = CanvasItem("event:course_1:7", CanvasItemType.EVENT, "高数", "习题课", startAt = clock.plusSeconds(3600))
            val first = CanvasSyncEngine.merge(empty, listOf(item), clock).state
            val second = CanvasSyncEngine.merge(first, listOf(item.copy(startAt = clock.plusSeconds(7200))), clock.plusSeconds(60)).state
            check(second.notices.size == 1 && second.notices.single().id == first.notices.single().id)
            check(second.notices.single().proposal.end == clock.plusSeconds(10800))
        }
        test("AI multi-item analysis creates separate review cards") {
            val proposals = listOf(
                Proposal(Action.CREATE_TASK, "实验四", minutes = 90, aiGenerated = true, confidence = .92, evidence = listOf("实验四")),
                Proposal(Action.CREATE_EVENT, "答疑", start = clock.plusSeconds(3600), end = clock.plusSeconds(7200), aiGenerated = true, confidence = .88),
            )
            val state = LocalEngine.ingestAnalyzed(empty, incoming("实验四稍后提交；今晚答疑"), proposals, clock)
            check(state.notices.size == 2 && state.notices.all { it.status == NoticeStatus.REVIEW && it.proposal.aiGenerated })
        }
        test("AI decomposition is preserved when task is confirmed") {
            val p = Proposal(Action.CREATE_TASK, "课程报告", minutes = 120, subTasks = listOf("查资料", "写初稿"), aiGenerated = true)
            val pending = LocalEngine.ingestAnalyzed(empty, incoming("完成课程报告"), listOf(p), clock)
            val applied = LocalEngine.apply(pending, pending.notices.single().id, p, clock)
            check(applied.tasks.single().subTasks.map { it.title } == listOf("查资料", "写初稿"))
        }
        test("local uncertainty decomposes confidence and allows only complete creation") {
            val input = incoming("实验四明天18:00前提交，预计2小时")
            val state = LocalEngine.ingestAnalyzed(empty, input, listOf(Proposal(Action.CREATE_TASK, "实验四",
                deadline = clock.plusSeconds(34 * 3600), minutes = 120, evidence = listOf("实验四", "明天18:00前提交"),
                aiGenerated = true, confidence = .93)), clock)
            val assessed = state.notices.single().proposal
            check(assessed.uncertainty != null && assessed.uncertainty!!.blockingFields.isEmpty())
            check(assessed.uncertainty!!.fields.time >= .9 && assessed.autoSafe)
        }
        test("uncertainty blocks conflicting actions and asks at most two useful questions") {
            val input = incoming("实验四取消，不用提交了")
            val proposal = Proposal(Action.CREATE_TASK, "实验四", aiGenerated = true, confidence = .95)
            val assessed = UncertaintyEngine.assess(input, proposal, empty)
            check("动作" in assessed.uncertainty!!.blockingFields)
            check(assessed.questions.isNotEmpty() && assessed.questions.size <= 2 && !assessed.autoSafe)
        }
        test("missing update target becomes a blocking field") {
            val input = incoming("实验四延期到明天")
            val assessed = UncertaintyEngine.assess(input, Proposal(Action.UPDATE_TASK, "实验四",
                deadline = clock.plusSeconds(24 * 3600), aiGenerated = true, confidence = .9, evidence = listOf("实验四")), empty)
            check("目标事项" in assessed.uncertainty!!.blockingFields)
            check(assessed.questions.any { "选择" in it })
        }
        test("personal duration learning uses completed actual samples") {
            val history = listOf(
                Task(title = "机器学习实验一", status = TaskStatus.COMPLETED, actualMinutes = 100),
                Task(title = "机器学习实验二", status = TaskStatus.COMPLETED, actualMinutes = 140),
                Task(title = "英语阅读", status = TaskStatus.COMPLETED, actualMinutes = 20),
            )
            check(IntelligenceEngine.durationSuggestion("机器学习实验三", empty.copy(tasks = history)) == 140)
        }
        test("personal model learns a conservative category duration multiplier") {
            val history = (1..6).map { index -> Task(title = "编程实验$index", category = TaskCategory.PROGRAMMING,
                minutes = 100, originalEstimateMinutes = 100, status = TaskStatus.COMPLETED, actualMinutes = 160) }
            val suggestion = PersonalTimeModel.durationSuggestion("新的编程实验", "", TaskCategory.PROGRAMMING, 3, 100,
                empty.copy(tasks = history))!!
            check(suggestion.minutes in 130..160 && suggestion.multiplier > 1.25 && suggestion.sampleCount >= 6) { suggestion.toString() }
        }
        test("personal model learns preferred time buckets from execution outcomes") {
            val task = Task(title = "编程实验", category = TaskCategory.PROGRAMMING, deadline = clock.plusSeconds(48 * 3600))
            val morning = clock.plusSeconds(3600)
            val night = clock.plusSeconds(14 * 3600)
            val history = (1..5).flatMap { index -> listOf(
                ExecutionRecord(taskId = "old-$index", category = TaskCategory.PROGRAMMING, group = "", plannedStart = morning.minusSeconds(index * 86400L), plannedMinutes = 60, outcome = ExecutionOutcome.COMPLETED),
                ExecutionRecord(taskId = "old-n-$index", category = TaskCategory.PROGRAMMING, group = "", plannedStart = night.minusSeconds(index * 86400L), plannedMinutes = 60, outcome = ExecutionOutcome.SKIPPED),
            ) }
            val modelState = empty.copy(tasks = listOf(task), executionHistory = history)
            check(PersonalTimeModel.slotScore(task, morning, modelState) > PersonalTimeModel.slotScore(task, night, modelState))
            check(PersonalTimeModel.bestWindow(task, modelState)?.label?.startsWith("上午") == true)
        }
        test("execution feedback reduces remaining work and survives replanning input") {
            val task = Task(title = "课程报告", minutes = 90, remaining = 90, category = TaskCategory.REPORT)
            val block = Block(taskId = task.id, start = clock, end = clock.plusSeconds(1800))
            val state = empty.copy(tasks = listOf(task), schedule = Schedule(blocks = listOf(block)))
            val next = PersonalTimeModel.record(state, block.id, ExecutionOutcome.COMPLETED, 40, clock.plusSeconds(1800))
            check(next.tasks.single().remaining == 50)
            check(next.executionHistory.single().actualMinutes == 40 && next.schedule.blocks.isEmpty())
        }
        test("local intelligence flags learned underestimation and repeated deadline changes") {
            val history = Task(title = "课程报告初稿", status = TaskStatus.COMPLETED, actualMinutes = 180)
            val active = Task(title = "课程报告终稿", minutes = 60, remaining = 60, deadlineChanges = 2, deadline = clock.plusSeconds(48 * 3600))
            val risks = IntelligenceEngine.risks(empty.copy(tasks = listOf(history, active)), clock)
            check(risks.any { "历史实际用时" in it.message } && risks.any { "变更 2 次" in it.message })
        }
        test("explicit auto-create preference creates and schedules") {
            val state = LocalEngine.ingest(empty.copy(preferences = prefs.copy(autoCreate = true)), incoming("实验三明天18:00提交，预计2小时"), clock)
            check(state.tasks.size == 1 && state.schedule.blocks.isNotEmpty() && state.notices.single().status == NoticeStatus.APPLIED)
        }
        test("confirmed notification preserves publication time on task") {
            val published = clock.minusSeconds(1800)
            val pending = LocalEngine.ingest(empty, incoming("实验三明天18:00提交，预计2小时").copy(receivedAt = published), clock)
            val notice = pending.notices.single()
            val applied = LocalEngine.apply(pending, notice.id, notice.proposal, clock)
            check(applied.tasks.single().releasedAt == published)
        }
        test("manual task creation records its release time once") {
            val draft = Task(title = "手动任务")
            val created = LocalEngine.saveTask(empty, draft, clock)
            val edited = LocalEngine.saveTask(created, created.tasks.single().copy(minutes = 90), clock.plusSeconds(600))
            check(created.tasks.single().releasedAt == clock)
            check(edited.tasks.single().releasedAt == clock)
        }
        test("Canvas publication time becomes task release baseline") {
            val published = clock.minusSeconds(86400)
            val item = CanvasItem("assignment:1:10", CanvasItemType.ASSIGNMENT, "机器学习", "实验五",
                dueAt = clock.plusSeconds(86400), publishedAt = published, updatedAt = clock)
            val imported = CanvasSyncEngine.merge(empty, listOf(item), clock).state
            check(imported.notices.single().input.receivedAt == published)
            val notice = imported.notices.single()
            val applied = LocalEngine.apply(imported, notice.id, notice.proposal, clock)
            check(applied.tasks.single().releasedAt == published)
        }
        test("completion timing separates total cycle from actual work") {
            val task = Task(title = "课程报告", status = TaskStatus.COMPLETED, releasedAt = clock,
                completedAt = clock.plusSeconds(6 * 3600), deadline = clock.plusSeconds(24 * 3600),
                actualMinutes = 90, originalEstimateMinutes = 120)
            val timing = CompletionTimingEngine.timing(task)!!
            check(timing.releaseToCompletionMinutes == 360L)
            check(timing.nonExecutionGapMinutes == 270L)
            check(timing.deadlineWindowUsage == .25 && timing.onTime == true && timing.estimateMultiple == 3.0)
        }
        test("completion timing summarizes distribution and active age") {
            val completed = listOf(60L, 600L, 2880L).mapIndexed { index, lead -> Task(
                title = "报告$index", category = if (index < 2) TaskCategory.REPORT else TaskCategory.PROGRAMMING,
                status = TaskStatus.COMPLETED, releasedAt = clock, completedAt = clock.plusSeconds(lead * 60),
                deadline = clock.plusSeconds((if (index == 2) 1440L else 1200L) * 60),
            ) }
            val summary = CompletionTimingEngine.summary(completed)!!
            check(summary.sampleCount == 3 && summary.medianMinutes == 600L && summary.p80Minutes == 1968L)
            check(kotlin.math.abs(summary.within24HoursRate - 2.0 / 3.0) < .0001)
            check(summary.onTimeRate == 2.0 / 3.0 && summary.categories.size == 2)
            val active = Task(title = "仍在进行", releasedAt = clock.minusSeconds(3600))
            check(CompletionTimingEngine.activeAgeMinutes(active, clock) == 60L)
            check(CompletionTimingEngine.summary(listOf(Task(title = "旧任务", status = TaskStatus.COMPLETED, completedAt = clock))) == null)
        }
        test("confirm once; repeated apply rejected") {
            val state = LocalEngine.ingest(empty, incoming("实验三明天提交"), clock)
            val notice = state.notices.single()
            val applied = LocalEngine.apply(state, notice.id, notice.proposal, clock)
            check(applied.tasks.size == 1 && applied.tasks.single().sourceIds == listOf(notice.id))
            fail { LocalEngine.apply(applied, notice.id, notice.proposal, clock) }
        }
        test("deadline lock and absent deadline preserve existing date") {
            val t = task().copy(deadlineLocked = true)
            val state = LocalEngine.ingest(empty.copy(tasks = listOf(t)), incoming("实验三延期到明天"), clock)
            val n = state.notices.single()
            check(LocalEngine.apply(state, n.id, n.proposal, clock).tasks.single().deadline == t.deadline)
            val unresolved = LocalEngine.ingest(empty.copy(tasks = listOf(t.copy(deadlineLocked = false))), incoming("实验三延期，具体时间另行通知"), clock)
            val u = unresolved.notices.single()
            check(LocalEngine.apply(unresolved, u.id, u.proposal, clock).tasks.single().deadline == t.deadline)
        }
        test("missing update target never creates a new task") {
            val s = LocalEngine.ingest(empty, incoming("实验四延期到明天"), clock)
            fail { LocalEngine.apply(s, s.notices.single().id, s.notices.single().proposal, clock) }
            check(s.tasks.isEmpty())
        }
        test("cancellation removes future blocks") {
            val t = task(); val base = empty.copy(tasks = listOf(t))
            val planned = base.copy(schedule = LocalScheduler.plan(base, clock))
            val s = LocalEngine.ingest(planned, incoming("实验三取消不用交了"), clock)
            val next = LocalEngine.apply(s, s.notices.single().id, s.notices.single().proposal, clock)
            check(next.tasks.single().status == TaskStatus.CANCELLED && next.schedule.blocks.isEmpty())
        }
        test("fixed event avoided; deadline end boundary honored") {
            val t = task(minutes = 60).copy(deadline = clock.plusSeconds(135 * 60))
            val event = FixedEvent(title = "课程", start = clock, end = clock.plusSeconds(3600))
            val result = LocalScheduler.plan(empty.copy(tasks = listOf(t), events = listOf(event)), clock)
            check(result.risks.isEmpty()); check(result.blocks.all { it.start >= event.end && it.end <= t.deadline })
            check(result.blocks.sumOf { Duration.between(it.start, it.end).toMinutes() } == 60L)
        }
        test("unsplittable task is not divided around a meeting") {
            val t = task(minutes = 120, hours = 3, split = false)
            val event = FixedEvent(title = "课", start = clock.plusSeconds(3600), end = clock.plusSeconds(7200))
            val s = LocalScheduler.plan(empty.copy(tasks = listOf(t), events = listOf(event)), clock)
            check(s.blocks.isEmpty() && s.risks.single().missingMinutes == 120)
        }
        test("locked time preserved and subtracted from remaining") {
            val t = task(minutes = 90)
            val b = Block(taskId = t.id, start = clock.plusSeconds(7200), end = clock.plusSeconds(10800), locked = true)
            val s = LocalScheduler.plan(empty.copy(tasks = listOf(t), schedule = Schedule(blocks = listOf(b))), clock)
            check(b in s.blocks); check(s.blocks.sumOf { Duration.between(it.start, it.end).toMinutes() } == 90L)
        }
        test("past deadline gives risk and no illegal block") {
            val t = task().copy(deadline = clock.minusSeconds(1))
            val s = LocalScheduler.plan(empty.copy(tasks = listOf(t)), clock)
            check(s.blocks.isEmpty() && s.risks.isNotEmpty())
        }
        test("completed task never gets new time") {
            check(LocalScheduler.plan(empty.copy(tasks = listOf(task().copy(status = TaskStatus.COMPLETED))), clock).blocks.isEmpty())
        }
        test("locked event collision explicitly reported") {
            val t = task(); val b = Block(taskId = t.id, start = clock, end = clock.plusSeconds(3600), locked = true)
            val e = FixedEvent(title = "课", start = b.start, end = b.end)
            val s = LocalScheduler.plan(empty.copy(tasks = listOf(t), events = listOf(e), schedule = Schedule(blocks = listOf(b))), clock)
            check(b in s.blocks && s.risks.isNotEmpty())
        }
        test("slot rounding never starts in past") {
            val s = LocalScheduler.plan(empty.copy(tasks = listOf(task(minutes = 1))), clock.plusSeconds(60))
            check(s.blocks.single().start == clock.plusSeconds(1800))
            check(Duration.between(s.blocks.single().start, s.blocks.single().end).toMinutes() == 30L)
        }
        test("same semantic reminder is not repeated after replan") {
            val t = task(); val b = Block(taskId = t.id, start = clock, end = clock.plusSeconds(3600))
            val state = empty.copy(tasks = listOf(t), schedule = Schedule(blocks = listOf(b)))
            val first = ReminderPlan.pending(state, clock).single()
            val updated = state.copy(schedule = Schedule(blocks = listOf(b.copy(id = "different-id"))), reminded = setOf(first.key))
            check(ReminderPlan.pending(updated, clock).isEmpty())
        }
        test("disabled or stale reminders suppressed") {
            val e = FixedEvent(title = "会", start = clock.minusSeconds(1800), end = clock.plusSeconds(3600))
            check(ReminderPlan.pending(empty.copy(events = listOf(e)), clock).isEmpty())
            check(ReminderPlan.pending(empty.copy(preferences = prefs.copy(reminders = false), events = listOf(e.copy(start = clock))), clock).isEmpty())
        }
        test("randomized 100 schedules preserve collision and deadline invariants") {
            repeat(100) { seed ->
                val random = Random(seed)
                val tasks = (0 until 8).map { task("T$it", random.nextInt(1, 240), random.nextLong(1, 30), random.nextBoolean()) }
                val e = FixedEvent(title = "Busy", start = clock.plusSeconds(3600), end = clock.plusSeconds(7200))
                val result = LocalScheduler.plan(empty.copy(tasks = tasks, events = listOf(e)), clock)
                result.blocks.forEachIndexed { i, b ->
                    check(b.start >= clock && b.end <= tasks.first { it.id == b.taskId }.deadline!!)
                    check(!LocalScheduler.overlaps(b.start, b.end, e.start, e.end))
                    check(result.blocks.drop(i + 1).none { LocalScheduler.overlaps(b.start, b.end, it.start, it.end) })
                }
            }
        }
        println("$count core checks passed (including 100 randomized scheduling cases)")
    }
}
