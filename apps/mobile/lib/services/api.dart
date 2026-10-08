import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

class Api {
  String baseUrl = '';
  String token = '';
  Future<dynamic> request(String method, String path, [Object? body]) async {
    final request = http.Request(method, Uri.parse('$baseUrl/api/v1$path'));
    request.headers['Content-Type'] = 'application/json';
    if (token.isNotEmpty) request.headers['Authorization'] = 'Bearer $token';
    if (body != null) request.body = jsonEncode(body);
    final client = http.Client();
    try {
      final response = await http.Response.fromStream(await client.send(request).timeout(const Duration(seconds: 90)));
      dynamic data;
      try { data = jsonDecode(utf8.decode(response.bodyBytes)); } catch (_) {
        throw ApiException('服务返回格式不正确，请检查服务器地址');
      }
      if (response.statusCode >= 400) {
        final detail = data is Map ? data['detail'] : null;
        throw ApiException(detail is String ? detail : '请求失败（${response.statusCode}），请检查填写内容');
      }
      return data;
    } on ApiException { rethrow; }
    catch (_) { throw ApiException('无法连接服务器，请检查网络、地址和后端运行状态'); }
    finally { client.close(); }
  }
}
