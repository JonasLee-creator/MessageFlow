import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../services/store.dart';

String dateLabel(dynamic value, {bool time = true}) {
  final date = value == null ? null : DateTime.tryParse(value.toString())?.toLocal();
  return date == null ? '未设置' : DateFormat(time ? 'M月d日 HH:mm' : 'M月d日').format(date);
}

Future<DateTime?> chooseDate(BuildContext context, DateTime? initial) async {
  final now = DateTime.now();
  final day = await showDatePicker(context: context, initialDate: initial ?? now, firstDate: DateTime(2020), lastDate: DateTime(2100));
  if (day == null || !context.mounted) return null;
  final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(initial ?? now));
  if (time == null) return null;
  return DateTime(day.year, day.month, day.day, time.hour, time.minute);
}

Future<Json?> taskForm(BuildContext context, [Json? existing]) async {
  final title = TextEditingController(text: existing?['title'] ?? '');
  final course = TextEditingController(text: existing?['course'] ?? '');
  final duration = TextEditingController(text: '${existing?['estimated_duration'] ?? 60}');
  final remaining = TextEditingController(text: '${existing?['remaining_duration'] ?? existing?['estimated_duration'] ?? 60}');
  var deadline = DateTime.tryParse(existing?['deadline'] ?? '')?.toLocal();
  bool splittable = existing?['splittable'] ?? true;
  bool deadlineLocked = existing?['deadline_locked'] ?? false;
  bool durationLocked = existing?['duration_locked'] ?? false;
  var priority = (existing?['priority'] ?? 5).toDouble();
  final form = GlobalKey<FormState>();
  final result = await showDialog<Json>(context: context, builder: (context) => StatefulBuilder(builder: (context, set) => AlertDialog(
    title: Text(existing == null ? '新建任务' : '编辑任务'),
    content: SizedBox(width: 420, child: Form(key: form, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
      TextFormField(controller: title, decoration: const InputDecoration(labelText: '任务名称'), maxLength: 512, validator: (v) => v!.trim().isEmpty ? '请填写名称' : null),
      TextFormField(controller: course, decoration: const InputDecoration(labelText: '课程 / 分组（可选）')),
      const SizedBox(height: 12),
      TextFormField(controller: duration, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '预计总耗时（分钟）'), validator: minuteValidator),
      if (existing != null) ...[const SizedBox(height: 12), TextFormField(controller: remaining, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '剩余耗时（分钟）'), validator: (v) => minuteValidator(v, zero: true))],
      ListTile(contentPadding: EdgeInsets.zero, title: const Text('截止时间'), subtitle: Text(dateLabel(deadline)), trailing: IconButton(icon: const Icon(Icons.clear), onPressed: () => set(() => deadline = null)), onTap: () async { final d = await chooseDate(context, deadline); if (d != null) set(() => deadline = d); }),
      Text('优先级 ${priority.round()} / 10'),
      Slider(value: priority, min: 1, max: 10, divisions: 9, onChanged: (v) => set(() => priority = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('允许拆分到多个时间段'), value: splittable, onChanged: (v) => set(() => splittable = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('锁定截止时间'), subtitle: const Text('外部消息不自动修改'), value: deadlineLocked, onChanged: (v) => set(() => deadlineLocked = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('锁定预计耗时'), value: durationLocked, onChanged: (v) => set(() => durationLocked = v)),
    ])))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')), FilledButton(onPressed: () {
      if (!form.currentState!.validate()) return;
      Navigator.pop(context, {'title': title.text.trim(), 'course': course.text.trim(), 'description': existing?['description'] ?? '', 'deadline': deadline?.toUtc().toIso8601String(),
        'estimated_duration': int.parse(duration.text), 'remaining_duration': existing == null ? int.parse(duration.text) : int.parse(remaining.text), 'priority': priority.round(), 'splittable': splittable, 'deadline_locked': deadlineLocked, 'duration_locked': durationLocked});
    }, child: const Text('保存并排程'))],
  )));
  title.dispose(); course.dispose(); duration.dispose(); remaining.dispose();
  return result;
}

String? minuteValidator(String? text, {bool zero = false}) {
  final value = int.tryParse(text ?? '');
  return value == null || value < (zero ? 0 : 1) || value > 20160 ? '请输入 ${zero ? 0 : 1}–20160 之间的整数' : null;
}

Future<Json?> eventForm(BuildContext context, [Json? existing]) async {
  final title = TextEditingController(text: existing?['title'] ?? '');
  var start = DateTime.tryParse(existing?['start_at'] ?? '')?.toLocal() ?? DateTime.now().add(const Duration(hours: 1));
  var end = DateTime.tryParse(existing?['end_at'] ?? '')?.toLocal() ?? start.add(const Duration(hours: 1));
  String? error;
  final result = await showDialog<Json>(context: context, builder: (context) => StatefulBuilder(builder: (context, set) => AlertDialog(
    title: Text(existing == null ? '添加固定日程' : '编辑日程'),
    content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
      TextField(controller: title, maxLength: 512, decoration: const InputDecoration(labelText: '课程、会议或考试')),
      ListTile(title: const Text('开始'), subtitle: Text(dateLabel(start)), onTap: () async {final d = await chooseDate(context, start); if (d != null) set(() => start = d);}),
      ListTile(title: const Text('结束'), subtitle: Text(dateLabel(end)), onTap: () async {final d = await chooseDate(context, end); if (d != null) set(() => end = d);}),
      if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
    ])),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')), FilledButton(onPressed: () {
      if (title.text.trim().isEmpty || !end.isAfter(start)) {set(() => error = '请填写名称，结束时间须晚于开始'); return;}
      Navigator.pop(context, {'title': title.text.trim(), 'start_at': start.toUtc().toIso8601String(), 'end_at': end.toUtc().toIso8601String(), 'event_type': existing?['event_type'] ?? 'course'});
    }, child: const Text('保存'))],
  )));
  title.dispose();
  return result;
}

Future<Json?> messageForm(BuildContext context) async {
  final channel = TextEditingController();
  final content = TextEditingController();
  final key = GlobalKey<FormState>();
  final result = await showDialog<Json>(context: context, builder: (context) => AlertDialog(
    title: const Text('粘贴一条通知'),
    content: SizedBox(width: 420, child: Form(key: key, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
      TextFormField(controller: channel, decoration: const InputDecoration(labelText: '课程 / 群名（可选）')),
      const SizedBox(height: 12), TextFormField(controller: content, minLines: 4, maxLines: 8, maxLength: 20000, decoration: const InputDecoration(labelText: '通知内容', hintText: '实验三延期到下周一提交'), validator: (v) => v!.trim().isEmpty ? '请粘贴通知' : null),
      const Text('内容将发送到你配置的服务器进行识别。'),
    ])))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')), FilledButton(onPressed: () {if (key.currentState!.validate()) Navigator.pop(context, {'platform': 'manual', 'channel_name': channel.text.trim(), 'content': content.text.trim(), 'source_updated_at': DateTime.now().toUtc().toIso8601String()});}, child: const Text('识别通知'))],
  ));
  channel.dispose(); content.dispose(); return result;
}
