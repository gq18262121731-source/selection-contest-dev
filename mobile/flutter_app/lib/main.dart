import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'core/network/api_client.dart';
import 'core/network/server_endpoint_config.dart';
import 'core/theme/app_colors.dart';
import 'features/auth/providers/auth_provider.dart';
import 'features/auth/repositories/auth_repository.dart';
import 'features/auth/screens/login_screen.dart';
import 'features/alarm/repositories/alarm_repository.dart';
import 'features/alarm/providers/alarm_provider.dart';
import 'features/alarm/widgets/global_alarm_listener.dart';
import 'features/voice/repositories/voice_repository.dart';
import 'features/voice/providers/voice_provider.dart';
import 'features/voice/providers/omni_7b_voice_provider.dart';
import 'features/care/providers/care_provider.dart';
import 'features/care/repositories/care_repository.dart';
import 'features/care/screens/elder_home_screen.dart';
import 'features/care/screens/family_home_screen.dart';
import 'features/health/repositories/health_repository.dart';
import 'features/session/services/session_manager.dart';
import 'features/agent/repositories/agent_repository.dart';
import 'features/agent/providers/agent_provider.dart';
import 'core/services/audio_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final sessionManager = SessionManager(prefs);
  final endpointConfig = ServerEndpointConfig(prefs);

  runApp(
    AppBootstrap(
      sessionManager: sessionManager,
      endpointConfig: endpointConfig,
    ),
  );
}

class AppBootstrap extends StatelessWidget {
  final SessionManager sessionManager;
  final ServerEndpointConfig endpointConfig;

  const AppBootstrap({
    super.key,
    required this.sessionManager,
    required this.endpointConfig,
  });

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider.value(value: sessionManager),
        ChangeNotifierProvider.value(value: endpointConfig),
        ProxyProvider2<SessionManager, ServerEndpointConfig, ApiClient>(
          update: (_, session, endpoint, __) => ApiClient(
            endpointConfig: endpoint,
            sessionManager: session,
            onUnauthorized: () {
              // 处理 401 全局重定向
            },
          ),
        ),
        ProxyProvider<ApiClient, AuthRepository>(
          update: (_, client, __) => AuthRepository(client),
        ),
        ProxyProvider<ApiClient, CareRepository>(
          update: (_, client, __) => CareRepository(client),
        ),
        ProxyProvider2<ApiClient, ServerEndpointConfig, AlarmRepository>(
          update: (_, client, endpoint, __) => AlarmRepository(
            client,
            endpointConfig: endpoint,
          ),
        ),
        ProxyProvider<ApiClient, VoiceRepository>(
          update: (_, client, __) => VoiceRepository(client),
        ),
        ProxyProvider2<ApiClient, ServerEndpointConfig, HealthRepository>(
          update: (_, client, endpoint, __) => HealthRepository(
            client,
            endpointConfig: endpoint,
          ),
        ),
        ProxyProvider<ApiClient, AgentRepository>(
          update: (_, client, __) => AgentRepository(client),
        ),
        Provider<AudioService>(
          create: (_) => AudioService(),
          dispose: (_, service) => service.dispose(),
        ),
        ChangeNotifierProxyProvider2<AuthRepository, SessionManager, AuthProvider>(
          create: (context) => AuthProvider(
            context.read<AuthRepository>(),
            context.read<SessionManager>(),
          ),
          update: (context, authRepo, session, prevAuth) =>
              prevAuth ?? AuthProvider(authRepo, session),
        ),
        ChangeNotifierProxyProvider2<CareRepository, SessionManager, CareProvider>(
          create: (context) => CareProvider(
            context.read<CareRepository>(),
            context.read<SessionManager>(),
          ),
          update: (context, repo, session, prev) {
            final provider = prev ?? CareProvider(repo, session);
            provider.updateDependencies(repo, session);
            return provider;
          },
        ),
        ChangeNotifierProxyProvider<AlarmRepository, AlarmProvider>(
          create: (context) => AlarmProvider(context.read<AlarmRepository>()),
          update: (context, repo, prev) => prev ?? AlarmProvider(repo),
        ),
        ChangeNotifierProxyProvider2<VoiceRepository, AudioService, VoiceProvider>(
          create: (context) => VoiceProvider(
            context.read<VoiceRepository>(),
            context.read<AudioService>(),
          ),
          update: (context, repo, audio, prev) {
            final provider = prev ?? VoiceProvider(repo, audio);
            provider.updateDependencies(repo, audio);
            return provider;
          },
        ),
        ChangeNotifierProxyProvider2<AgentRepository, AudioService, AgentProvider>(
          create: (context) => AgentProvider(
            context.read<AgentRepository>(),
            context.read<AudioService>(),
          ),
          update: (context, repo, audio, prev) {
            final provider = prev ?? AgentProvider(repo, audio);
            provider.updateDependencies(repo, audio);
            return provider;
          },
        ),
        ChangeNotifierProvider<Omni7bVoiceProvider>(
          create: (context) {
            const apiKey = 'sk-67d1be1cac0649b9a8839d2328bbb845';
            const apiBase = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
            return Omni7bVoiceProvider(
              apiKey: apiKey,
              apiBase: apiBase,
              audioService: context.read<AudioService>(),
            );
          },
        ),
      ],
      child: const AiHealthApp(),
    );
  }
}

class AiHealthApp extends StatefulWidget {
  const AiHealthApp({super.key});

  @override
  State<AiHealthApp> createState() => _AiHealthAppState();
}

class _AiHealthAppState extends State<AiHealthApp> {
  AuthProvider? _authProvider;
  AlarmProvider? _alarmProvider;
  bool _didScheduleSessionCheck = false;

  @override
  void initState() {
    super.initState();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final authProvider = context.read<AuthProvider>();
    _alarmProvider ??= context.read<AlarmProvider>();
    if (!identical(_authProvider, authProvider)) {
      _authProvider?.removeListener(_handleAuthChanged);
      _authProvider = authProvider;
      _authProvider?.addListener(_handleAuthChanged);
      WidgetsBinding.instance.addPostFrameCallback((_) => _handleAuthChanged());
    }
    if (!_didScheduleSessionCheck && _authProvider != null) {
      _didScheduleSessionCheck = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _authProvider?.checkSession();
      });
    }
  }

  @override
  void dispose() {
    _authProvider?.removeListener(_handleAuthChanged);
    super.dispose();
  }

  void _handleAuthChanged() {
    if (!mounted) {
      return;
    }

    final authProvider = _authProvider;
    if (authProvider == null) {
      return;
    }

    final alarmProvider = _alarmProvider;
    if (alarmProvider == null) {
      return;
    }

    final role = authProvider.user?.role.toLowerCase();
    final shouldListenForAlarms =
        authProvider.status == AuthStatus.authenticated && role != 'elder';

    if (shouldListenForAlarms) {
      alarmProvider.ensureStarted();
      return;
    }

    alarmProvider.reset();
  }

  @override
  Widget build(BuildContext context) {
    final authStatus = context.watch<AuthProvider>().status;

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AIoT Health',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.primary,
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: AppColors.background,
        useMaterial3: true,
        fontFamily: 'Inter', // Ensuring modern typography
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.transparent,
          elevation: 0,
          centerTitle: true,
          iconTheme: IconThemeData(color: AppColors.textMain),
          titleTextStyle: TextStyle(
            color: AppColors.textMain,
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),
        cardTheme: CardThemeData(
          color: AppColors.cardBg,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppColors.border, width: 1),
          ),
          margin: const EdgeInsets.only(bottom: 16),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.primary,
            foregroundColor: Colors.white,
            elevation: 0,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.primary,
            side: const BorderSide(color: AppColors.primary, width: 1.5),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
        dialogTheme: DialogThemeData(
          backgroundColor: AppColors.surface,
          elevation: 8,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: AppColors.border),
          ),
          titleTextStyle: const TextStyle(
            color: AppColors.textMain,
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
          contentTextStyle: const TextStyle(
            color: AppColors.textSub,
            fontSize: 16,
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: AppColors.surface,
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: AppColors.border),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: AppColors.primary, width: 2),
          ),
          labelStyle: const TextStyle(color: AppColors.textSub),
          hintStyle: const TextStyle(color: AppColors.textMuted),
        ),
      ),
      home: GlobalAlarmListener(
        child: _buildHome(context, authStatus),
      ),
    );
  }

  Widget _buildHome(BuildContext context, AuthStatus status) {
    if (status == AuthStatus.initial) {
      return const Scaffold(
        backgroundColor: Color(0xFFF8FAFC),
        body: Center(child: CircularProgressIndicator(color: Color(0xFF2563EB))),
      );
    }

    if (status == AuthStatus.authenticated) {
      final user = context.read<AuthProvider>().user;
      if (user?.role == 'elder') {
        return const ElderHomeScreen();
      }
      return const FamilyHomeScreen();
    }

    return const LoginScreen();
  }
}
