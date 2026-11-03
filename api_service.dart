import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Single point of contact with the Flask backend.
///
/// CHANGE THIS to your machine's LAN address before running on a phone.
/// `localhost` on a phone means the phone itself, not your laptop.
///   Windows: ipconfig    → IPv4 Address
///   Mac:     ifconfig    → inet under en0
/// Android emulator uses 10.0.2.2 to reach the host machine.
class ApiService {
  static const String baseUrl = 'https://web-production-833a1.up.railway.app';

  static String? _token;
  static Map<String, dynamic>? _user;

  static bool get isAuthenticated => _token != null;
  static Map<String, dynamic>? get currentUser => _user;
  static String get userName => _user?['name'] ?? '';
  static bool get isAdmin => _user?['is_admin'] == true;

  // ------------------------------------------------------------- session

  static Future<void> loadSession() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('token');
    final raw = prefs.getString('user');
    if (raw != null) {
      try {
        _user = jsonDecode(raw) as Map<String, dynamic>;
      } catch (_) {
        _user = null;
      }
    }
  }

  static Future<void> _saveSession(String token, Map<String, dynamic> user) async {
    _token = token;
    _user = user;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('token', token);
    await prefs.setString('user', jsonEncode(user));
  }

  static Future<void> signOut() async {
    _token = null;
    _user = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('token');
    await prefs.remove('user');
  }

  // ------------------------------------------------------------ plumbing

  static Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_token != null) 'Authorization': 'Bearer $_token',
  };

  static const _timeout = Duration(seconds: 15);

  /// Every call funnels through here so error handling lives in one place.
  static Future<dynamic> _send(
      String method,
      String path, {
        Map<String, dynamic>? body,
      }) async {
    final uri = Uri.parse('$baseUrl$path');

    try {
      late http.Response res;
      final payload = body == null ? null : jsonEncode(body);

      switch (method) {
        case 'GET':
          res = await http.get(uri, headers: _headers).timeout(_timeout);
          break;
        case 'POST':
          res = await http
              .post(uri, headers: _headers, body: payload)
              .timeout(_timeout);
          break;
        case 'PUT':
          res = await http
              .put(uri, headers: _headers, body: payload)
              .timeout(_timeout);
          break;
        case 'DELETE':
          res = await http.delete(uri, headers: _headers).timeout(_timeout);
          break;
        default:
          throw ApiException('Unsupported method $method');
      }

      final decoded = res.body.isEmpty ? null : jsonDecode(res.body);

      if (res.statusCode >= 200 && res.statusCode < 300) {
        return decoded;
      }

      // The token expired, was rejected, or the account was blocked — clear
      // it so the app returns to login rather than retrying with a dead
      // credential.
      final blocked = decoded is Map && decoded['blocked'] == true;
      if (res.statusCode == 401 || blocked) {
        await signOut();
      }

      final message = decoded is Map && decoded['error'] != null
          ? decoded['error'] as String
          : 'Request failed (${res.statusCode})';
      throw ApiException(message, statusCode: res.statusCode);
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException(
        'Could not reach the server. Check that it is running and that '
            'your phone is on the same network.',
      );
    }
  }

  // ---------------------------------------------------------------- auth

  static Future<void> signUp({
    required String name,
    required String email,
    required String phone,
    required String password,
    String? bloodGroup,
    String? vehicleType,
    String? vehicleNumber,
    String? drivingPreference,
    String? fcmToken,
  }) async {
    final res = await _send('POST', '/api/signup', body: {
      'name': name,
      'email': email,
      'phone': phone,
      'password': password,
      'blood_group': bloodGroup,
      'vehicle_type': vehicleType,
      'vehicle_number': vehicleNumber,
      'driving_preference': drivingPreference,
      'fcm_token': fcmToken,
    });

    await _saveSession(res['token'] as String,
        res['user'] as Map<String, dynamic>);
  }

  static Future<void> logIn({
    required String email,
    required String password,
    String? fcmToken,
  }) async {
    final res = await _send('POST', '/api/login', body: {
      'email': email,
      'password': password,
      'fcm_token': fcmToken,
    });

    await _saveSession(res['token'] as String,
        res['user'] as Map<String, dynamic>);
  }

  // ------------------------------------------------------------- profile

  static Future<Map<String, dynamic>> getProfile() async {
    final res = await _send('GET', '/api/profile');
    _user = res as Map<String, dynamic>;
    return res;
  }

  static Future<Map<String, dynamic>> updateProfile(
      Map<String, dynamic> changes) async {
    final res = await _send('PUT', '/api/profile', body: changes);
    _user = res['user'] as Map<String, dynamic>;
    return _user!;
  }

  /// Called on every launch — FCM rotates tokens and stale ones fail silently.
  static Future<void> uploadFcmToken(String token) async {
    if (!isAuthenticated) return;
    try {
      await _send('POST', '/api/fcm-token', body: {'fcm_token': token});
    } catch (_) {
      // Not worth interrupting the user over; it retries next launch.
    }
  }

  // ----------------------------------------------------------- guardians

  static Future<List<Map<String, dynamic>>> getGuardians() async {
    final res = await _send('GET', '/api/guardians');
    return (res as List).cast<Map<String, dynamic>>();
  }

  static Future<Map<String, dynamic>> addGuardian({
    required String name,
    required String phone,
    String relation = 'Contact',
  }) async {
    final res = await _send('POST', '/api/guardians', body: {
      'name': name,
      'phone': phone,
      'relation': relation,
    });
    return res['guardian'] as Map<String, dynamic>;
  }

  static Future<void> deleteGuardian(int id) =>
      _send('DELETE', '/api/guardians/$id');

  // ------------------------------------------------------------- hazards

  static Future<Map<String, dynamic>> reportHazard({
    required String type,
    required double latitude,
    required double longitude,
    String severity = 'Moderate',
    String? note,
    String? placeName,
  }) async {
    final res = await _send('POST', '/api/hazards', body: {
      'type': type,
      'latitude': latitude,
      'longitude': longitude,
      'severity': severity,
      'note': note,
      'place_name': placeName,
    });
    return res as Map<String, dynamic>;
  }

  static Future<List<Map<String, dynamic>>> nearbyHazards({
    required double lat,
    required double lng,
    double radiusKm = 10,
  }) async {
    final res = await _send(
      'GET',
      '/api/hazards/nearby?lat=$lat&lng=$lng&radius_km=$radiusKm',
    );
    return (res as List).cast<Map<String, dynamic>>();
  }

  static Future<void> confirmHazard(int id) =>
      _send('POST', '/api/hazards/$id/confirm');

  // ------------------------------------------------------------ journeys

  static Future<int> startJourney({
    double? originLat,
    double? originLng,
    double? destLat,
    double? destLng,
    String? destinationName,
    double distanceKm = 0,
    int durationMin = 0,
  }) async {
    final res = await _send('POST', '/api/journeys/start', body: {
      'origin_lat': originLat,
      'origin_lng': originLng,
      'destination_lat': destLat,
      'destination_lng': destLng,
      'destination_name': destinationName,
      'distance_km': distanceKm,
      'duration_min': durationMin,
    });
    return res['journey']['id'] as int;
  }

  static Future<void> endJourney(
      int journeyId, {
        double topSpeedKph = 0,
        int overspeedEvents = 0,
        double? distanceKm,
      }) =>
      _send('POST', '/api/journeys/$journeyId/end', body: {
        'top_speed_kph': topSpeedKph,
        'overspeed_events': overspeedEvents,
        'distance_km': distanceKm,
      });

  static Future<List<Map<String, dynamic>>> journeyHistory() async {
    final res = await _send('GET', '/api/journeys?limit=20');
    return (res as List).cast<Map<String, dynamic>>();
  }

  // ----------------------------------------------------------------- sos

  static Future<Map<String, dynamic>> triggerSos({
    required double latitude,
    required double longitude,
    String? placeName,
    String trigger = 'manual',
  }) async {
    final res = await _send('POST', '/api/sos', body: {
      'latitude': latitude,
      'longitude': longitude,
      'place_name': placeName,
      'trigger': trigger,
    });
    return res as Map<String, dynamic>;
  }

  static Future<void> resolveSos(int alertId) =>
      _send('POST', '/api/sos/$alertId/resolve');

  static Future<Map<String, dynamic>> sosAlert(int alertId) async {
    final res = await _send('GET', '/api/sos/$alertId');
    return res as Map<String, dynamic>;
  }

  /// Pushed by the person in trouble while their alert is open, so guardians
  /// watching the responder map see them move.
  static Future<void> updateSosLocation(
      int alertId, {
        required double latitude,
        required double longitude,
        String? placeName,
      }) =>
      _send('POST', '/api/sos/$alertId/location', body: {
        'latitude': latitude,
        'longitude': longitude,
        'place_name': placeName,
      });

  static Future<List<Map<String, dynamic>>> incomingAlerts() async {
    final res = await _send('GET', '/api/sos/incoming');
    return (res as List).cast<Map<String, dynamic>>();
  }

  // --------------------------------------------------------------- admin

  static Future<Map<String, dynamic>> adminStats() async {
    final res = await _send('GET', '/api/admin/stats');
    return res as Map<String, dynamic>;
  }

  static Future<List<Map<String, dynamic>>> adminUsers({
    String query = '',
    String status = 'all',
  }) async {
    final res = await _send(
      'GET',
      '/api/admin/users?q=${Uri.encodeComponent(query)}&status=$status',
    );
    return (res as List).cast<Map<String, dynamic>>();
  }

  static Future<Map<String, dynamic>> adminUserDetail(int id) async {
    final res = await _send('GET', '/api/admin/users/$id');
    return res as Map<String, dynamic>;
  }

  static Future<void> adminBlockUser(int id, String reason) =>
      _send('POST', '/api/admin/users/$id/block', body: {'reason': reason});

  static Future<void> adminUnblockUser(int id) =>
      _send('POST', '/api/admin/users/$id/unblock');

  static Future<List<Map<String, dynamic>>> adminSosAlerts({
    String status = 'all',
  }) async {
    final res = await _send('GET', '/api/admin/sos?status=$status');
    return (res as List).cast<Map<String, dynamic>>();
  }

  static Future<void> adminResolveSos(int id) =>
      _send('POST', '/api/admin/sos/$id/resolve');

  static Future<List<Map<String, dynamic>>> adminHazards({
    String status = 'active',
  }) async {
    final res = await _send('GET', '/api/admin/hazards?status=$status');
    return (res as List).cast<Map<String, dynamic>>();
  }

  static Future<void> adminDeleteHazard(int id) =>
      _send('DELETE', '/api/admin/hazards/$id');

  static Future<Map<String, dynamic>> adminBroadcast({
    required String title,
    required String body,
  }) async {
    final res = await _send('POST', '/api/admin/broadcast',
        body: {'title': title, 'body': body});
    return res as Map<String, dynamic>;
  }
}

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}
