import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:marg/screens/journey/journey_history.dart';
import 'package:marg/screens/privacy.dart';

import 'firebase_options.dart';
import 'core/app_theme.dart';
import 'services/api_service.dart';
import 'services/push_service.dart';
import 'screens/splash_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/signup_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/journey/plan_journey_screen.dart';
import 'screens/journey/live_map_screen.dart';
import 'screens/hazard/report_hazard_screen.dart';
import 'screens/weather/weather_screen.dart';
import 'screens/sos/sos_screen.dart';
import 'screens/sos/guardians_screen.dart';
import 'screens/profile/profile_screen.dart';
import 'screens/admin_screen.dart';


/// Lets a notification tap navigate from outside the widget tree.
final navigatorKey = GlobalKey<NavigatorState>();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  // Must be registered before runApp.
  FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);

  // Restore the saved session first, so PushService knows whether it can
  // upload the FCM token straight away or has to wait for login.
  await ApiService.loadSession();

  PushService.navigatorKey = navigatorKey;
  await PushService.initialize();

  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
  ));

  runApp(const MargApp());
}

class MargApp extends StatelessWidget {
  const MargApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MARG',
      debugShowCheckedModeBanner: false,
      navigatorKey: navigatorKey,
      theme: AppTheme.dark,
      initialRoute: '/',
      routes: {
        '/': (_) => const SplashScreen(),
        '/login': (_) => const LoginScreen(),
        '/signup': (_) => const SignupScreen(),
        '/home': (_) => const HomeScreen(),
        '/plan': (_) => const PlanJourneyScreen(),
        '/live': (_) => const LiveMapScreen(),
        '/report': (_) => const ReportHazardScreen(),
        '/weather': (_) => const WeatherScreen(),
        '/sos': (_) => const SosScreen(),
        '/guardians': (_) => const GuardiansScreen(),
        '/profile': (_) => const ProfileScreen(),
        '/admin': (_) => const AdminScreen(),
        '/history': (_) => const JourneyHistoryScreen(),
        '/privacy': (_) => const PrivacyScreen(),
      },
    );
  }
}
