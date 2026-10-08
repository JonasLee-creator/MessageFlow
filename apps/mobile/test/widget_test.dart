import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:chronoflow/main.dart';
import 'package:chronoflow/services/store.dart';

void main() {
  testWidgets('demo is explicitly labeled and all five destinations open', (tester) async {
    await tester.pumpWidget(ChronoFlowApp(store: AppStore()));
    await tester.pumpAndSettle();
    expect(find.text('界面示例 · 数据未连接服务器'), findsOneWidget);
    for (final label in ['发现', '任务', '日历', '连接', '今天']) {
      await tester.tap(find.widgetWithText(NavigationDestination, label));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    }
  });
}
