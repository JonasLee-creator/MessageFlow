import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'screens/home.dart';
import 'services/store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(ChronoFlowApp(store: AppStore()));
}

const ink = Color(0xFF192E32);
const teal = Color(0xFF16776A);
const canvas = Color(0xFFF5F7F4);

class ChronoFlowApp extends StatelessWidget {
  final AppStore store;
  const ChronoFlowApp({super.key, required this.store});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'ChronoFlow 时序', debugShowCheckedModeBanner: false,
    locale: const Locale('zh', 'CN'),
    supportedLocales: const [Locale('zh', 'CN'), Locale('en')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    theme: ThemeData(useMaterial3: true, scaffoldBackgroundColor: canvas,
      colorScheme: ColorScheme.fromSeed(seedColor: teal, primary: teal, surface: canvas),
      appBarTheme: const AppBarTheme(backgroundColor: canvas, foregroundColor: ink, centerTitle: false, elevation: 0),
      inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: Colors.white,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFFDDE5DF))),
        contentPadding: const EdgeInsets.all(16)),
      navigationBarTheme: const NavigationBarThemeData(backgroundColor: Colors.white, indicatorColor: Color(0xFFDCEDE5)),
    ),
    home: Home(store: store),
  );
}
