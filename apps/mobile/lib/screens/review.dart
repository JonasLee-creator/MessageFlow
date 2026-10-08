import 'package:flutter/material.dart';
import '../services/store.dart';
import 'forms.dart';

Future<Json?> reviewForm(BuildContext context, Json raw, AppStore store) async {
  final original = Map<String, dynamic>.from(raw['decision']);
  var action = original['action'] as String;
  String? target = original['target_id'];
  final task = Map<String, dynamic>.from(original['task'] ?? {});
  final event = Map<String, dynamic>.from(original['event'] ?? {});
  final title = TextEditingController(text: task['title'] ?? event['title'] ?? '');
  final duration = TextEditingController(text: '${task['estimated_duration_minutes'] ?? 60}');
  DateTime? deadline = DateTime.tryParse(task['deadline'] ?? '')?.toLocal();
  bool deadlinePresent = task.containsKey('deadline');
  DateTime? start = DateTime.tryParse(event['start_at'] ?? '')?.toLocal();
  DateTime? end = DateTime.tryParse(event['end_at'] ?? '')?.toLocal();
  String? error;
  final labels = {'CREATE_TASK': '新建任务', 'UPDATE_TASK': '更新任务', 'CANCEL_TASK': '取消任务', 'CREATE_EVENT': '新建日程', 'UPDATE_EVENT': '更新日程', 'CANCEL_EVENT': '取消日程', 'IGNORE': '忽略'};
  final result = await showDialog<Json>(context: context, builder: (context) => StatefulBuilder(builder: (context, set) {
    final isEvent = action.endsWith('EVENT');
    final needsTarget = action.startsWith('UPDATE') || action.startsWith('CANCEL');
    final isCancel = action.startsWith('CANCEL') || action == 'IGNORE';
    final targets = isEvent ? store.events : store.activeTasks;
    if (!targets.any((t) => t['id'] == target)) target = null;
    return AlertDialog(title: const Text('核对识别结果'), content: SizedBox(width: 440, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
      DropdownButtonFormField<String>(value: action, isExpanded: true, items: labels.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(), onChanged: (v) => set(() {action = v!; target = null;})),
      const SizedBox(height: 16),
      if (needsTarget) DropdownButtonFormField<String>(value: target, isExpanded: true, decoration: const InputDecoration(labelText: '对应的已有对象'), items: targets.map((t) => DropdownMenuItem<String>(value: t['id'], child: Text(t['title'], overflow: TextOverflow.ellipsis))).toList(), onChanged: (v) => set(() => target = v)),
      if (!isCancel) ...[
        const SizedBox(height: 16), TextField(controller: title, decoration: InputDecoration(labelText: action.startsWith('UPDATE') && !isEvent ? '标题（留空保留原值）' : '标题')),
        if (!isEvent) ...[
          const SizedBox(height: 16), TextField(controller: duration, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '预计耗时（分钟）')),
          ListTile(title: Text(deadlinePresent ? '截止时间' : '截止时间（保持原值）'), subtitle: Text(dateLabel(deadline)), onTap: () async {final d = await chooseDate(context, deadline); if (d != null) set(() {deadline = d; deadlinePresent = true;});}),
          TextButton(onPressed: () => set(() {deadline = null; deadlinePresent = true;}), child: const Text('清除截止时间')),
        ] else ...[
          ListTile(title: const Text('开始时间'), subtitle: Text(dateLabel(start)), onTap: () async {final d = await chooseDate(context, start); if (d != null) set(() => start = d);}),
          ListTile(title: const Text('结束时间'), subtitle: Text(dateLabel(end)), onTap: () async {final d = await chooseDate(context, end); if (d != null) set(() => end = d);}),
        ],
      ],
      if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
      const SizedBox(height: 8), const Text('确认后更新个人计划并重新排程。任务中锁定的日期与耗时仍会保留。', style: TextStyle(fontSize: 12, color: Colors.black54)),
    ]))), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('返回')), FilledButton(onPressed: () {
      if (needsTarget && target == null) {set(() => error = '请选择对应对象'); return;}
      if (!isCancel && ((action.startsWith('CREATE') || isEvent) && title.text.trim().isEmpty)) {set(() => error = '请填写标题'); return;}
      if (!isCancel && isEvent && (start == null || end == null || !end!.isAfter(start!))) {set(() => error = '请设置有效的开始、结束时间'); return;}
      if (!isCancel && !isEvent && minuteValidator(duration.text) != null) {set(() => error = minuteValidator(duration.text)); return;}
      Navigator.pop(context, {
        'action': action, 'confidence': original['confidence'], 'target_id': needsTarget ? target : null,
        'reason': '${original['reason'] ?? ''}（用户已核对）', 'requires_confirmation': false,
        if (!isCancel && !isEvent) 'task': {
          if (title.text.trim().isNotEmpty) 'title': title.text.trim(),
          if (task['course'] != null) 'course': task['course'],
          if (deadlinePresent) 'deadline': deadline?.toUtc().toIso8601String(),
          if (action == 'CREATE_TASK' || task.containsKey('estimated_duration_minutes') || duration.text != '60') 'estimated_duration_minutes': int.parse(duration.text),
        },
        if (!isCancel && isEvent) 'event': {'title': title.text.trim(), 'start_at': start!.toUtc().toIso8601String(), 'end_at': end!.toUtc().toIso8601String(), 'event_type': event['event_type'] ?? 'course'},
      });
    }, child: const Text('确认应用'))]);
  }));
  title.dispose(); duration.dispose(); return result;
}
