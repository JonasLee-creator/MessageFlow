import 'package:flutter/services.dart';

class NativeBridge {
  static const channel = MethodChannel('com.chronoflow/notifications');
  static Future<Map<String, dynamic>> settings() async {
    try { return Map<String, dynamic>.from(await channel.invokeMethod('getSettings') ?? {}); }
    on MissingPluginException { return {}; }
  }
  static Future<void> configure(Map<String, dynamic> values) => channel.invokeMethod('configure', values);
  static Future<void> openAccess() => channel.invokeMethod('openNotificationAccess');
  static Future<void> retry() => channel.invokeMethod('retryUploads');
  static Future<void> exportCalendar(String title, DateTime start, DateTime end) => channel.invokeMethod('exportCalendar', {
    'title': title, 'start': start.millisecondsSinceEpoch, 'end': end.millisecondsSinceEpoch,
  });
}
