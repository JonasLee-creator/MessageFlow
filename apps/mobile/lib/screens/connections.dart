import 'package:flutter/material.dart';
import '../services/store.dart';
import '../services/native_bridge.dart';
import 'forms.dart';

class Connections extends StatefulWidget {
  final AppStore store;
  const Connections({super.key, required this.store});
  @override
  State<Connections> createState() => _ConnectionsState();
}

class _ConnectionsState extends State<Connections> {
  final url = TextEditingController(text: 'http://10.0.2.2:8000');
  final username = TextEditingController();
  final password = TextEditingController();
  final groups = TextEditingController();
  bool register = false;
  AppStore get s => widget.store;
  @override
  void dispose() {url.dispose(); username.dispose(); password.dispose(); groups.dispose(); super.dispose();}
  Widget box(List<Widget> children) => Container(margin: const EdgeInsets.only(bottom: 18), padding: const EdgeInsets.all(20), decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22)), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children));

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(22), physics: const AlwaysScrollableScrollPhysics(), children: [
    const Text('CONNECTED, ON YOUR TERMS', style: TextStyle(color: Color(0xFF16776A), fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
    const SizedBox(height: 8), const Text('连接，你的信息。', style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800)),
    const SizedBox(height: 8), const Text('你决定来源，时序负责整理。', style: TextStyle(color: Colors.black54)), const SizedBox(height: 24),
    box([
      const Text('ChronoFlow 服务器', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)), const SizedBox(height: 15),
      if (s.demo) ...[
        TextField(controller: url, keyboardType: TextInputType.url, autocorrect: false, decoration: const InputDecoration(labelText: '后端地址', helperText: '模拟器：10.0.2.2；真机：电脑局域网 IP')),
        const SizedBox(height: 12), TextField(controller: username, autocorrect: false, decoration: const InputDecoration(labelText: '用户名（至少 3 个字符）')),
        const SizedBox(height: 12), TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: '密码（至少 8 个字符）')),
        const SizedBox(height: 12), SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('注册新账户'), value: register, onChanged: s.busy ? null : (v) => setState(() => register = v)),
        FilledButton(onPressed: s.busy ? null : () async {final ok = await s.login(url.text.trim(), username.text.trim(), password.text, register); if (ok) password.clear();}, child: Text(register ? '注册并连接' : '登录并连接')),
      ] else ...[
        Text(s.api.baseUrl, style: const TextStyle(color: Color(0xFF16776A))),
        const SizedBox(height: 8), const Text('账户数据保存在服务器，访问令牌保存在 Android Keystore 加密存储中。', style: TextStyle(fontSize: 12, height: 1.5)),
        TextButton(onPressed: s.busy ? null : () => s.run(() async {await s.logout();}), child: const Text('退出登录并停止通知采集')),
      ],
    ]),
    box([
      const Row(children: [Icon(Icons.school_outlined, color: Color(0xFF16776A)), SizedBox(width: 10), Text('Canvas', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold))]),
      const SizedBox(height: 12), const Text('导入课程作业与公告。后端每 5 分钟同步一次，也可立即同步。', style: TextStyle(color: Colors.black54, height: 1.5)),
      for (final connector in s.connectors) ...[
        const Divider(height: 28), Text(connector['base_url'], style: const TextStyle(fontWeight: FontWeight.w600)),
        Text(connector['enabled'] == true ? '上次同步：${dateLabel(connector['last_synced_at'])}' : '已断开连接', style: const TextStyle(fontSize: 12)),
        if (connector['error'] != null) Text(connector['error'], style: const TextStyle(color: Colors.red, fontSize: 12)),
        Row(children: [TextButton(onPressed: s.busy || connector['enabled'] != true ? null : () => s.mutate('POST', '/connectors/${connector['id']}/sync'), child: const Text('立即同步')), TextButton(onPressed: s.busy || connector['enabled'] != true ? null : () => s.mutate('DELETE', '/connectors/${connector['id']}'), child: const Text('断开'))]),
      ],
      const SizedBox(height: 12), OutlinedButton(onPressed: s.demo || s.busy ? null : connectCanvas, child: const Text('连接 Canvas')),
    ]),
    box([
      const Row(children: [Icon(Icons.notifications_active_outlined, color: Color(0xFF16776A)), SizedBox(width: 10), Text('微信课程群通知', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold))]),
      const SizedBox(height: 12), const Text('开启后，仅将下方白名单群名匹配且包含作业、考试等关键词的通知上传到你的服务器。系统通知权限可看到其他通知，本应用会在手机上过滤掉它们。', style: TextStyle(fontSize: 12, height: 1.6, color: Colors.black54)),
      const SizedBox(height: 12), Text('系统通知访问：${s.native['accessGranted'] == true ? '已授权' : '未授权'}'),
      TextButton(onPressed: s.demo || s.busy ? null : () => s.run(() async {await NativeBridge.openAccess();}), child: const Text('打开 Android 通知访问设置')),
      TextField(controller: groups, minLines: 2, maxLines: 5, decoration: InputDecoration(labelText: '课程群白名单（每行一个，需与通知标题完全一致）', hintText: ((s.native['groups'] ?? []) as List).join('\n'))),
      const SizedBox(height: 12), OutlinedButton(onPressed: s.demo || s.busy ? null : () => s.run(() async {
        final values = groups.text.split('\n').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
        if (values.isEmpty) throw Exception('请先填写至少一个课程群名');
        await NativeBridge.configure({'groups': values}); s.native = await NativeBridge.settings();
      }), child: const Text('保存白名单')),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('允许采集并上传'), subtitle: Text('当前白名单：${((s.native['groups'] ?? []) as List).join('、')}'), value: s.native['enabled'] == true && !s.demo, onChanged: s.demo || s.busy ? null : (v) => s.run(() async {
        if (v && s.native['accessGranted'] != true) throw Exception('请先授予系统通知访问权限');
        if (v && ((s.native['groups'] ?? []) as List).isEmpty) throw Exception('请先保存课程群白名单');
        await NativeBridge.configure({'enabled': v}); s.native = await NativeBridge.settings();
      })),
      Text('待上传 ${s.native['pendingCount'] ?? 0} 条 · 停止采集会清空本地队列', style: const TextStyle(fontSize: 12, color: Colors.black54)),
      if ((s.native['uploadError'] ?? '').toString().isNotEmpty) Text(s.native['uploadError'], style: const TextStyle(fontSize: 12, color: Colors.red)),
      TextButton(onPressed: s.demo || s.busy ? null : () => s.run(() async {await NativeBridge.retry(); s.native = await NativeBridge.settings();}), child: const Text('重试待上传通知')),
    ]),
    const Padding(padding: EdgeInsets.only(bottom: 20), child: Text('ChronoFlow 0.1.0 · Android V1\n通知被微信隐藏、群聊免打扰或系统限制时，无法读取未展示的内容，可使用「发现 → 录入通知」。', textAlign: TextAlign.center, style: TextStyle(color: Colors.black45, fontSize: 11, height: 1.6))),
  ]);

  Future<void> connectCanvas() async {
    final base = TextEditingController();
    final token = TextEditingController();
    final data = await showDialog<Json>(context: context, builder: (context) => AlertDialog(title: const Text('连接学校 Canvas'), content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
      TextField(controller: base, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: '学校地址', hintText: 'https://school.instructure.com')),
      const SizedBox(height: 12), TextField(controller: token, obscureText: true, decoration: const InputDecoration(labelText: 'Canvas Access Token')),
      const SizedBox(height: 12), const Text('V1 使用学校允许的个人访问令牌。令牌加密保存在后端，学校禁用令牌时暂不能连接。', style: TextStyle(fontSize: 12)),
    ])), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')), FilledButton(onPressed: () => Navigator.pop(context, {'base_url': base.text.trim(), 'access_token': token.text.trim()}), child: const Text('连接'))]));
    base.dispose(); token.dispose();
    if (data != null) await s.mutate('POST', '/connectors/canvas', data);
  }
}
