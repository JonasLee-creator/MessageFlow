import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../services/store.dart';
import '../services/native_bridge.dart';
import 'forms.dart';
import 'review.dart';
import 'connections.dart';

const _teal = Color(0xFF16776A);
const _ink = Color(0xFF192E32);

class Home extends StatefulWidget {
  final AppStore store;
  const Home({super.key, required this.store});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with WidgetsBindingObserver {
  int tab = 0;
  DateTime selectedDay = DateTime.now();
  AppStore get s => widget.store;
  @override
  void initState() {
    super.initState(); WidgetsBinding.instance.addObserver(this); s.initialize();
  }
  @override
  void dispose() { WidgetsBinding.instance.removeObserver(this); super.dispose(); }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) { if (state == AppLifecycleState.resumed) s.refresh(); }

  Future<void> newItem() async {
    if (s.demo) {setState(() => tab = 4); return;}
    if (tab == 1) {
      final data = await messageForm(context);
      if (data != null) await s.mutate('POST', '/ingest', data);
    } else if (tab == 3) {
      final data = await eventForm(context);
      if (data != null) await s.mutate('POST', '/events', data);
    } else {
      final data = await taskForm(context);
      if (data != null) await s.mutate('POST', '/tasks', data);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(listenable: s, builder: (context, _) => Scaffold(
    appBar: AppBar(title: Row(children: [
      Container(width: 34, height: 34, decoration: BoxDecoration(color: _teal, borderRadius: BorderRadius.circular(11)), child: const Icon(Icons.all_inclusive, color: Colors.white, size: 24)),
      const SizedBox(width: 10), const Text('ChronoFlow', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: -.6)),
      const SizedBox(width: 8), const Text('时序', style: TextStyle(fontSize: 13, color: _teal)),
    ]), actions: [IconButton(tooltip: '刷新', onPressed: s.busy ? null : s.refresh, icon: const Icon(Icons.refresh))]),
    body: SafeArea(child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 800), child: Column(children: [
      if (s.busy) const LinearProgressIndicator(minHeight: 2),
      if (s.demo) Material(color: const Color(0xFFE8F0E6), child: ListTile(dense: true, leading: const Icon(Icons.science_outlined, size: 20), title: const Text('界面示例 · 数据未连接服务器'), trailing: TextButton(onPressed: () => setState(() => tab = 4), child: const Text('去连接')))),
      if (s.error != null) Material(color: const Color(0xFFFFE8DE), child: ListTile(title: Text(s.error!, style: const TextStyle(fontSize: 13)), trailing: IconButton(icon: const Icon(Icons.close), onPressed: () {s.error = null; setState(() {});}))),
      Expanded(child: RefreshIndicator(onRefresh: () async {await s.refresh();}, child: IndexedStack(index: tab, children: [today(), discoveries(), taskList(), calendar(), Connections(store: s)]))),
    ])))),
    floatingActionButton: tab == 4 ? null : FloatingActionButton.extended(onPressed: s.busy ? null : newItem, backgroundColor: _teal, foregroundColor: Colors.white,
      icon: Icon(tab == 1 ? Icons.auto_awesome : Icons.add), label: Text(tab == 1 ? '录入通知' : tab == 3 ? '固定日程' : '新建任务')),
    bottomNavigationBar: NavigationBar(selectedIndex: tab, onDestinationSelected: (v) => setState(() => tab = v), destinations: [
      const NavigationDestination(icon: Icon(Icons.wb_sunny_outlined), selectedIcon: Icon(Icons.wb_sunny), label: '今天'),
      NavigationDestination(icon: Badge(isLabelVisible: s.pending > 0, label: Text('${s.pending}'), child: const Icon(Icons.inbox_outlined)), label: '发现'),
      const NavigationDestination(icon: Icon(Icons.checklist_rounded), label: '任务'),
      const NavigationDestination(icon: Icon(Icons.calendar_month_outlined), label: '日历'),
      const NavigationDestination(icon: Icon(Icons.hub_outlined), label: '连接'),
    ]),
  ));

  Widget page(List<Widget> children) => ListView(padding: const EdgeInsets.fromLTRB(22, 24, 22, 100), physics: const AlwaysScrollableScrollPhysics(), children: children);
  Widget heading(String eyebrow, String title, String sub) => Padding(padding: const EdgeInsets.only(bottom: 22), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(eyebrow, style: const TextStyle(color: _teal, fontSize: 11, letterSpacing: 2.2, fontWeight: FontWeight.w700)),
    const SizedBox(height: 8), Text(title, style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w800, color: _ink, height: 1.2)),
    const SizedBox(height: 8), Text(sub, style: const TextStyle(color: Color(0xFF75817C), height: 1.5)),
  ]));
  Widget section(String text, [Widget? trailing]) => Padding(padding: const EdgeInsets.symmetric(vertical: 16), child: Row(children: [Expanded(child: Text(text, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17, color: _ink))), if (trailing != null) trailing]));
  Widget card(Widget child, {Color color = Colors.white}) => Container(margin: const EdgeInsets.only(bottom: 12), padding: const EdgeInsets.all(18), decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(20), border: Border.all(color: const Color(0xFFE3E9E2))), child: child);
  Widget empty(String title, String sub) => card(Column(children: [const SizedBox(height: 15), const Icon(Icons.spa_outlined, size: 40, color: _teal), const SizedBox(height: 14), Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)), const SizedBox(height: 8), Text(sub, textAlign: TextAlign.center), const SizedBox(height: 15)]));

  List<Json> entriesFor(DateTime day) {
    bool inDay(Json row) {
      final a = DateTime.parse(row['start_at']).toLocal();
      final b = DateTime.parse(row['end_at']).toLocal();
      final start = DateTime(day.year, day.month, day.day);
      return a.isBefore(start.add(const Duration(days: 1))) && b.isAfter(start);
    }
    final rows = [...s.events.map((e) => {...e, 'fixed': true}), ...s.blocks.map((b) => {...b, 'title': s.taskTitle(b['task_id']), 'fixed': false})].where(inDay).toList();
    rows.sort((a, b) => DateTime.parse(a['start_at']).compareTo(DateTime.parse(b['start_at'])));
    return rows;
  }

  Widget today() {
    final entries = entriesFor(DateTime.now());
    final minutes = entries.where((e) => e['fixed'] != true).fold<int>(0, (sum, e) => sum + DateTime.parse(e['end_at']).difference(DateTime.parse(e['start_at'])).inMinutes);
    return page([
      heading(DateFormat('EEEE · M月d日', 'zh_CN').format(DateTime.now()), '把今天，安排从容。', '让信息成为行动，让时间留给重要的事。'),
      Container(padding: const EdgeInsets.all(22), decoration: BoxDecoration(color: _ink, borderRadius: BorderRadius.circular(24)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [Icon(Icons.auto_awesome, color: Color(0xFFA6D9C1), size: 18), SizedBox(width: 8), Text('你的今日节奏', style: TextStyle(color: Color(0xFFA6D9C1)))]),
        const SizedBox(height: 22), Row(children: [metric('${entries.length}', '日程安排'), metric('${(minutes / 60).toStringAsFixed(1)} h', '计划专注'), metric('${s.activeTasks.length}', '进行中任务')]),
        const SizedBox(height: 20), const Divider(color: Color(0xFF40534F)), const SizedBox(height: 6),
        Text(s.demo ? '示例排程 · 连接服务器后开始你的计划' : '排程 v${s.schedule['version']} · 未来 14 天滚动安排', style: const TextStyle(color: Colors.white70, fontSize: 12)),
      ])),
      if (s.pending > 0) Padding(padding: const EdgeInsets.only(top: 16), child: InkWell(onTap: () => setState(() => tab = 1), borderRadius: BorderRadius.circular(20), child: card(Row(children: [const Icon(Icons.mark_email_unread_outlined, color: _teal), const SizedBox(width: 14), Expanded(child: Text('${s.pending} 条新发现，等待你确认', style: const TextStyle(fontWeight: FontWeight.w600))), const Icon(Icons.arrow_forward, size: 20)]), color: const Color(0xFFEBF3EA)))),
      ...riskCards(),
      section('今天的时间线', TextButton(onPressed: () => setState(() => tab = 3), child: const Text('全部日历 →'))),
      if (entries.isEmpty) empty('今天还没有安排', '添加任务或固定日程，时序会为你规划可用时间。'),
      ...entries.map(timeline),
    ]);
  }

  Widget metric(String number, String label) => Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(number, style: const TextStyle(color: Colors.white, fontSize: 25, fontWeight: FontWeight.w700)), const SizedBox(height: 6), Text(label, style: const TextStyle(color: Colors.white60, fontSize: 11))]));

  List<Widget> riskCards() => (s.schedule['risks'] as List).map<Widget>((r) => Padding(padding: const EdgeInsets.only(top: 12), child: card(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    const Row(children: [Icon(Icons.warning_amber_rounded, color: Color(0xFFAF642B)), SizedBox(width: 8), Text('当前条件下无法完成排程', style: TextStyle(fontWeight: FontWeight.bold))]),
    const SizedBox(height: 8), Text('${r['title'] ?? ''} ${r['reason'] ?? ''}'),
    if (r['required_minutes'] != null) Text('需要 ${r['required_minutes']} 分钟 · 可用 ${r['available_minutes']} 分钟'),
  ]), color: const Color(0xFFFFF0DE)))).toList();

  Widget timeline(Json row) {
    final fixed = row['fixed'] == true;
    final color = fixed ? const Color(0xFF9B793E) : _teal;
    return InkWell(onTap: () => entryDetails(row), borderRadius: BorderRadius.circular(20), child: card(Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(width: 50, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(DateFormat('HH:mm').format(DateTime.parse(row['start_at']).toLocal()), style: const TextStyle(fontWeight: FontWeight.bold)), const SizedBox(height: 4), Text(DateFormat('HH:mm').format(DateTime.parse(row['end_at']).toLocal()), style: const TextStyle(fontSize: 12, color: Colors.grey))])),
      Container(width: 3, height: 43, margin: const EdgeInsets.symmetric(horizontal: 14), decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(row['title'], style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)), const SizedBox(height: 6), Text(fixed ? '固定日程 · 为你预留时间' : '专注时间 · ${row['locked'] == true ? '已锁定' : '可自动调整'}', style: TextStyle(color: color, fontSize: 12))])),
      Icon(fixed ? Icons.school_outlined : row['locked'] == true ? Icons.lock_outline : Icons.more_horiz, size: 19, color: color),
    ])));
  }

  Future<void> entryDetails(Json row) async {
    await showModalBottomSheet(context: context, showDragHandle: true, builder: (context) => SafeArea(child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(row['title'], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 22)), const SizedBox(height: 8),
      Text('${dateLabel(row['start_at'])} — ${dateLabel(row['end_at'])}'), const SizedBox(height: 20),
      if (!s.demo && row['fixed'] != true) ListTile(leading: Icon(row['locked'] == true ? Icons.lock_open : Icons.lock), title: Text(row['locked'] == true ? '解锁，允许自动调整' : '锁定这个时间段'), onTap: () {Navigator.pop(context); s.mutate('PUT', '/schedule/blocks/${row['id']}/lock', {'locked': row['locked'] != true});}),
      if (!s.demo && row['fixed'] == true) ListTile(leading: const Icon(Icons.edit_outlined), title: const Text('编辑固定日程'), onTap: () async {Navigator.pop(context); final data = await eventForm(this.context, row); if (data != null) await s.mutate('PUT', '/events/${row['id']}', data);}),
      if (!s.demo && row['fixed'] == true) ListTile(leading: const Icon(Icons.delete_outline), title: const Text('取消固定日程'), onTap: () {Navigator.pop(context); s.mutate('DELETE', '/events/${row['id']}');}),
      ListTile(leading: const Icon(Icons.event_available), title: const Text('添加到系统日历'), subtitle: const Text('在系统日历中确认保存，不自动同步后续变更'), onTap: () {Navigator.pop(context); s.run(() => NativeBridge.exportCalendar(row['title'], DateTime.parse(row['start_at']), DateTime.parse(row['end_at'])));}),
    ]))));
  }

  Widget discoveries() => page([
    heading('INFORMATION → ACTION', '发现，值得行动的信息。', '每一次修改都有依据，每一条来源都可追溯。'),
    if (s.inbox.isEmpty) empty('收件箱是空的', '粘贴一条通知，或连接 Canvas 与课程群通知。'),
    ...s.inbox.map((raw) {
      final decision = raw['decision'] as Map?;
      final status = raw['status'];
      return card(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Icon(raw['platform'] == 'wechat' ? Icons.chat_bubble_outline : raw['platform'] == 'canvas' ? Icons.school_outlined : Icons.note_alt_outlined, color: _teal, size: 20), const SizedBox(width: 9), Expanded(child: Text(raw['channel_name'] == '' ? '手动录入' : raw['channel_name'], style: const TextStyle(fontWeight: FontWeight.w600))), statusChip(status)]),
        const SizedBox(height: 15), Text(raw['content'], style: const TextStyle(fontSize: 15, height: 1.6)),
        if (decision != null) ...[
          const SizedBox(height: 16), Wrap(spacing: 8, runSpacing: 6, children: [Chip(avatar: const Icon(Icons.auto_awesome, size: 15), label: Text(actionLabel(decision['action']))), Chip(label: Text('${((decision['confidence'] ?? 0) * 100).round()}% 置信度'))]),
          const SizedBox(height: 7), Text('${decision['reason'] ?? ''}', style: const TextStyle(color: Colors.black54, fontSize: 12, height: 1.5)),
          const SizedBox(height: 7), Text('识别方式：${raw['engine'] == 'local-rules' ? '本地规则（非 AI）' : raw['engine'] == 'example' ? '界面示例' : raw['engine'] == 'canvas-rule' ? 'Canvas 结构化数据' : 'AI 模型'}', style: const TextStyle(fontSize: 11, color: _teal)),
        ],
        if (raw['error'] != null) Text(raw['error'], style: const TextStyle(color: Colors.red)),
        if (status == 'needs_confirmation') ...[const SizedBox(height: 14), Row(children: [Expanded(child: OutlinedButton(onPressed: s.busy || s.demo ? null : () => s.mutate('POST', '/inbox/${raw['id']}/review', {'accept': false}), child: const Text('忽略'))), const SizedBox(width: 10), Expanded(child: FilledButton(onPressed: s.busy ? null : () async {if (s.demo) {setState(() => tab = 4); return;} final data = await reviewForm(context, raw, s); if (data != null) await s.mutate('POST', '/inbox/${raw['id']}/review', {'accept': true, 'decision': data});}, child: const Text('核对并确认')))])],
        if (status == 'failed') TextButton(onPressed: s.busy ? null : () => s.mutate('POST', '/inbox/${raw['id']}/retry'), child: const Text('重试识别')),
      ]));
    }),
  ]);

  Widget statusChip(String status) {
    final labels = {'needs_confirmation': '待确认', 'processed': '已应用', 'ignored': '已忽略', 'failed': '失败', 'queued': '排队中', 'processing': '识别中'};
    return Container(padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5), decoration: BoxDecoration(color: status == 'needs_confirmation' ? const Color(0xFFFFEDCE) : const Color(0xFFECF1EB), borderRadius: BorderRadius.circular(7)), child: Text(labels[status] ?? status, style: const TextStyle(fontSize: 11)));
  }

  Widget taskList() => page([
    heading('A LITTLE PROGRESS, EVERY DAY', '任务，心中有数。', '${s.activeTasks.length} 项进行中 · 更改任务后会自动重排'),
    if (s.tasks.isEmpty) empty('从第一件事开始', '写下任务和预计耗时，剩下的交给时间规划。'),
    ...s.tasks.map((task) {
      final done = task['status'] == 'completed' || task['status'] == 'cancelled';
      return card(Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        IconButton(tooltip: '标记完成', onPressed: done || s.demo || s.busy ? null : () => s.mutate('POST', '/tasks/${task['id']}/complete'), icon: Icon(done ? Icons.check_circle : Icons.radio_button_unchecked, color: done ? Colors.grey : _teal)),
        const SizedBox(width: 5), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(task['title'], style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, decoration: done ? TextDecoration.lineThrough : null, color: done ? Colors.grey : _ink)),
          const SizedBox(height: 8), Text('${task['course'] == '' ? '个人任务' : task['course']} · 剩余 ${task['remaining_duration']} 分钟', style: const TextStyle(fontSize: 12, color: Colors.black54)),
          const SizedBox(height: 6), Text('截止 ${dateLabel(task['deadline'])}', style: const TextStyle(fontSize: 12, color: _teal)),
          if (done) Text(task['status'] == 'completed' ? '已完成' : '已取消', style: const TextStyle(fontSize: 11, color: Colors.grey)),
        ])),
        PopupMenuButton<String>(enabled: !s.demo && !s.busy, onSelected: (action) async {
          if (action == 'edit') {final data = await taskForm(context, task); if (data != null) await s.mutate('PUT', '/tasks/${task['id']}', data);}
          if (action == 'cancel') await s.mutate('DELETE', '/tasks/${task['id']}');
          if (action == 'sources') await showSources(task);
        }, itemBuilder: (_) => [if (!done) const PopupMenuItem(value: 'edit', child: Text('编辑任务')), const PopupMenuItem(value: 'sources', child: Text('查看来源')), if (!done) const PopupMenuItem(value: 'cancel', child: Text('取消任务'))]),
      ]));
    }),
  ]);

  Future<void> showSources(Json task) async {
    List<dynamic> rows = [];
    final ok = await s.run(() async {rows = await s.api.request('GET', '/tasks/${task['id']}/sources');});
    if (!ok || !mounted) return;
    await showDialog(context: context, builder: (context) => AlertDialog(title: const Text('任务来源'), content: SizedBox(width: 400, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: rows.isEmpty ? [const Text('这是一项手动创建的任务。')] : rows.map<Widget>((r) => ListTile(title: Text(r['channel_name']), subtitle: Text(r['content']))).toList()))), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('关闭'))]));
  }

  Widget calendar() {
    final rows = entriesFor(selectedDay);
    final today = DateTime.now();
    return page([
      heading('MAKE ROOM FOR WHAT MATTERS', '日历，有条不紊。', '固定日程与专注时间，共用一张时间表。'),
      Row(children: [Expanded(child: Text('排程 v${s.schedule['version']}', style: const TextStyle(fontWeight: FontWeight.bold))), TextButton(onPressed: s.busy || s.demo ? null : showVersions, child: const Text('版本记录')), OutlinedButton.icon(onPressed: s.busy || s.demo ? null : () => s.mutate('POST', '/schedule/replan'), icon: const Icon(Icons.auto_awesome, size: 15), label: const Text('重排'))]),
      const SizedBox(height: 14), SizedBox(height: 80, child: ListView.separated(scrollDirection: Axis.horizontal, itemCount: 14, separatorBuilder: (_, index) => const SizedBox(width: 8), itemBuilder: (context, i) {
        final day = DateTime(today.year, today.month, today.day + i);
        final chosen = DateUtils.isSameDay(day, selectedDay);
        return InkWell(onTap: () => setState(() => selectedDay = day), borderRadius: BorderRadius.circular(16), child: Container(width: 54, decoration: BoxDecoration(color: chosen ? _teal : Colors.white, borderRadius: BorderRadius.circular(16)), child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [Text(i == 0 ? '今天' : DateFormat('E', 'zh_CN').format(day), style: TextStyle(fontSize: 11, color: chosen ? Colors.white70 : Colors.grey)), const SizedBox(height: 10), Text('${day.day}', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: chosen ? Colors.white : _ink))])));
      })),
      ...riskCards(), section(DateFormat('M月d日 EEEE', 'zh_CN').format(selectedDay)),
      if (rows.isEmpty) empty('这一天，还有很多可能', '暂无安排。添加任务后会自动寻找合适的时间。'),
      ...rows.map(timeline),
    ]);
  }

  Future<void> showVersions() async {
    List<dynamic> versions = [];
    final ok = await s.run(() async {versions = await s.api.request('GET', '/schedule/versions');});
    if (!ok || !mounted) return;
    await showDialog(context: context, builder: (context) => AlertDialog(title: const Text('排程历史'), content: SizedBox(width: 420, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: versions.map<Widget>((v) => ListTile(title: Text('v${v['version']} · ${v['status']}'), subtitle: Text('${v['trigger']}\n${dateLabel(v['created_at'])}'))).toList()))), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('关闭'))]));
  }
}

String actionLabel(String? action) => {'CREATE_TASK': '创建任务', 'UPDATE_TASK': '更新任务', 'CANCEL_TASK': '取消任务', 'CREATE_EVENT': '创建日程', 'UPDATE_EVENT': '更新日程', 'CANCEL_EVENT': '取消日程', 'IGNORE': '忽略信息'}[action] ?? '等待识别';
