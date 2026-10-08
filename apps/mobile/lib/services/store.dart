import 'package:flutter/foundation.dart';
import 'api.dart';
import 'native_bridge.dart';

typedef Json = Map<String, dynamic>;

class AppStore extends ChangeNotifier {
  final api = Api();
  bool demo = true;
  bool busy = false;
  String? error;
  List<Json> tasks = [], events = [], inbox = [], connectors = [];
  Json schedule = {'version': 0, 'status': 'EMPTY', 'risks': [], 'blocks': []};
  Json native = {};

  AppStore() { loadDemo(); }
  List<Json> get blocks => (schedule['blocks'] as List).map((e) => Map<String, dynamic>.from(e)).toList();
  List<Json> get activeTasks => tasks.where((t) => t['status'] != 'completed' && t['status'] != 'cancelled').toList();
  int get pending => inbox.where((r) => r['status'] == 'needs_confirmation').length;
  String taskTitle(String id) => tasks.where((t) => t['id'] == id).map((t) => t['title'].toString()).firstOrNull ?? '任务';

  Future<void> initialize() async {
    native = await NativeBridge.settings();
    api.baseUrl = native['baseUrl'] ?? '';
    api.token = native['token'] ?? '';
    if (api.baseUrl.isNotEmpty && api.token.isNotEmpty) {
      demo = false;
      tasks = []; events = []; inbox = []; connectors = [];
      schedule = {'version': 0, 'status': 'EMPTY', 'risks': [], 'blocks': []};
      await refresh();
    }
    notifyListeners();
  }

  Future<bool> run(Future<void> Function() action) async {
    if (busy) return false;
    busy = true; error = null; notifyListeners();
    try { await action(); return true; }
    catch (e) { error = e.toString(); return false; }
    finally { busy = false; notifyListeners(); }
  }

  Future<void> fetch() async {
    final values = await Future.wait([
      api.request('GET', '/tasks'), api.request('GET', '/events'),
      api.request('GET', '/inbox'), api.request('GET', '/schedule'), api.request('GET', '/connectors'),
    ]);
    List<Json> rows(dynamic v) => (v as List).map((e) => Map<String, dynamic>.from(e)).toList();
    tasks = rows(values[0]); events = rows(values[1]); inbox = rows(values[2]);
    schedule = Map<String, dynamic>.from(values[3]); connectors = rows(values[4]);
    native = await NativeBridge.settings();
  }
  Future<bool> refresh() => run(() async { if (!demo) await fetch(); });
  Future<bool> mutate(String method, String path, [Object? body]) => run(() async {
    if (demo) throw ApiException('当前是界面示例，请在「连接」中登录服务器后操作');
    final result = await api.request(method, path, body);
    if (result is Map && result['error'] != null) throw ApiException(result['error'].toString());
    await fetch();
  });

  Future<bool> login(String url, String username, String password, bool register) => run(() async {
    final parsed = Uri.tryParse(url);
    if (parsed == null || !['http', 'https'].contains(parsed.scheme) || parsed.host.isEmpty || parsed.userInfo.isNotEmpty || parsed.hasQuery || parsed.hasFragment || (parsed.path.isNotEmpty && parsed.path != '/')) {
      throw ApiException('请输入服务器根地址，例如 https://your-server.example');
    }
    if (kReleaseMode && parsed.scheme != 'https') throw ApiException('正式版必须使用 HTTPS 服务器');
    final previousUrl = api.baseUrl;
    final previousToken = api.token;
    try {
      api.baseUrl = url.replaceAll(RegExp(r'/+$'), ''); api.token = '';
      final result = await api.request('POST', register ? '/auth/register' : '/auth/login', {'username': username, 'password': password});
      api.token = result['access_token'];
      await NativeBridge.configure({'baseUrl': api.baseUrl, 'token': api.token, 'enabled': false});
    } catch (_) { api.baseUrl = previousUrl; api.token = previousToken; rethrow; }
    demo = false;
    tasks = []; events = []; inbox = []; connectors = [];
    schedule = {'version': 0, 'status': 'EMPTY', 'risks': [], 'blocks': []};
    await fetch();
  });

  Future<void> logout() async {
    await NativeBridge.configure({'token': '', 'enabled': false});
    api.token = ''; demo = true; error = null; loadDemo(); notifyListeners();
  }

  void loadDemo() {
    final now = DateTime.now();
    DateTime at(int day, int hour, [int minute = 0]) => DateTime(now.year, now.month, now.day + day, hour, minute);
    tasks = [
      {'id': 'demo-1', 'title': '计算机网络 · 实验三', 'course': '计算机网络', 'deadline': at(3, 23, 59).toIso8601String(), 'estimated_duration': 180, 'remaining_duration': 180, 'priority': 8, 'splittable': true, 'status': 'scheduled', 'deadline_locked': false, 'duration_locked': false},
      {'id': 'demo-2', 'title': '阅读与整理文献', 'course': '学术英语', 'deadline': at(5, 23, 59).toIso8601String(), 'estimated_duration': 60, 'remaining_duration': 60, 'priority': 5, 'splittable': true, 'status': 'scheduled', 'deadline_locked': false, 'duration_locked': false},
    ];
    events = [{'id': 'demo-e', 'title': '高等数学', 'start_at': at(0, 9).toIso8601String(), 'end_at': at(0, 10, 30).toIso8601String(), 'event_type': 'course'}];
    schedule = {'version': 3, 'status': 'OPTIMAL', 'risks': [], 'blocks': [
      {'id': 'demo-b1', 'task_id': 'demo-1', 'start_at': at(0, 16).toIso8601String(), 'end_at': at(0, 17, 30).toIso8601String(), 'locked': false},
      {'id': 'demo-b2', 'task_id': 'demo-2', 'start_at': at(0, 19).toIso8601String(), 'end_at': at(0, 20).toIso8601String(), 'locked': true},
      {'id': 'demo-b3', 'task_id': 'demo-1', 'start_at': at(1, 16).toIso8601String(), 'end_at': at(1, 17, 30).toIso8601String(), 'locked': false},
    ]};
    inbox = [{'id': 'demo-r', 'platform': 'wechat', 'channel_name': '计算机网络课程群', 'content': '老师：实验三延期到下周一提交。', 'status': 'needs_confirmation', 'engine': 'example', 'decision': {'action': 'UPDATE_TASK', 'confidence': 0.96, 'target_id': 'demo-1', 'reason': '示例：识别截止日期变更，确认后保留原任务并重新排程。', 'task': {'deadline': at(3, 23, 59).toUtc().toIso8601String()}}}];
    connectors = [];
  }
}
