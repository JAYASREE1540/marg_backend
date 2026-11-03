import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/app_theme.dart';
import '../../core/mock_data.dart';
import '../../core/widgets/app_controls.dart';
import '../../core/widgets/lane_divider.dart';
import '../../services/api_service.dart';
import '../../services/location_service.dart';
import '../../services/weather_service.dart';

class SosScreen extends StatefulWidget {
  final bool embedded;
  const SosScreen({super.key, this.embedded = false});

  @override
  State<SosScreen> createState() => _SosScreenState();
}

class _SosScreenState extends State<SosScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  bool _counting = false;
  bool _sending = false;
  int _seconds = 5;
  Timer? _timer;

  Map<String, dynamic>? _activeAlert;
  int _notifiedCount = 0;
  Timer? _locationPusher;

  List<Map<String, dynamic>> _guardians = [];
  bool _loadingGuardians = true;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat(reverse: true);
    _loadGuardians();
  }

  @override
  void dispose() {
    _pulse.dispose();
    _timer?.cancel();
    _locationPusher?.cancel();
    super.dispose();
  }

  /// While an alert is open, keep pushing position so the guardian's
  /// responder map tracks the person rather than showing a frozen pin.
  void _startLocationPushing(int alertId) {
    _locationPusher?.cancel();
    _locationPusher = Timer.periodic(const Duration(seconds: 12), (_) async {
      if (!mounted || _activeAlert == null) return;
      try {
        final p = await LocationService.current();
        await ApiService.updateSosLocation(
          alertId,
          latitude: p.latitude,
          longitude: p.longitude,
        );
      } catch (_) {
        // A dropped update isn't worth surfacing — the next one will land.
      }
    });
  }

  Future<void> _loadGuardians() async {
    try {
      final list = await ApiService.getGuardians();
      if (!mounted) return;
      setState(() {
        _guardians = list;
        _loadingGuardians = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loadingGuardians = false);
    }
  }

  void _beginCountdown() {
    HapticFeedback.heavyImpact();
    setState(() {
      _counting = true;
      _seconds = 5;
    });

    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return;
      if (_seconds <= 1) {
        t.cancel();
        _fireAlert();
      } else {
        HapticFeedback.selectionClick();
        setState(() => _seconds--);
      }
    });
  }

  void _cancelCountdown() {
    _timer?.cancel();
    setState(() => _counting = false);
  }

  Future<void> _fireAlert() async {
    HapticFeedback.heavyImpact();
    setState(() {
      _counting = false;
      _sending = true;
    });

    try {
      final status = await LocationService.ensurePermission();
      if (status != LocationStatus.granted) {
        throw ApiException(
            'MARG needs your location to send a useful SOS. ${status.message}');
      }

      final pos = await LocationService.current();
      final place =
      await WeatherService.placeName(pos.latitude, pos.longitude);

      final res = await ApiService.triggerSos(
        latitude: pos.latitude,
        longitude: pos.longitude,
        placeName: place,
      );

      if (!mounted) return;
      final alert = res['alert'] as Map<String, dynamic>;
      setState(() {
        _sending = false;
        _activeAlert = alert;
        _notifiedCount = res['guardians_notified'] as int;
      });
      _startLocationPushing(alert['id'] as int);
    } catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e is ApiException ? e.message : 'Could not send SOS'),
          backgroundColor: AppColors.danger,
        ),
      );
    }
  }

  Future<void> _standDown() async {
    final alert = _activeAlert;
    if (alert == null) return;

    setState(() => _sending = true);
    try {
      await ApiService.resolveSos(alert['id'] as int);
      _locationPusher?.cancel();
      if (!mounted) return;
      setState(() {
        _activeAlert = null;
        _sending = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  /// Opens the dialler pre-filled rather than placing the call, so an
  /// accidental tap never auto-dials emergency services.
  Future<void> _dial(String number) async {
    final uri = Uri(scheme: 'tel', path: number);
    try {
      final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not open the dialler for $number')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not open the dialler for $number')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final content = ListView(
      padding: EdgeInsets.fromLTRB(20, widget.embedded ? 16 : 8, 20, 32),
      children: [
        if (widget.embedded) ...[
          Text('EMERGENCY', style: AppTheme.eyebrow(color: AppColors.danger)),
          const SizedBox(height: 6),
          Text('SOS',
              style: AppTheme.display(28, weight: FontWeight.w900, spacing: 2)),
          const SizedBox(height: 4),
          Text('Holds your location open to your guardians.',
              style: AppTheme.body(13.5, color: AppColors.muted)),
          const SizedBox(height: 26),
        ],

        Center(child: _buildTrigger()),
        const SizedBox(height: 24),

        if (_activeAlert != null) _buildSentPanel() else _buildIdleHint(),

        const SizedBox(height: 30),

        const SectionHeader('Call directly'),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: 2.0,
          children: emergencyServices.map((s) {
            return Material(
              color: Colors.transparent,
              child: InkWell(
                borderRadius: BorderRadius.circular(14),
                onTap: () => _dial(s['number'] as String),
                child: Container(
                  padding:
                  const EdgeInsets.symmetric(horizontal: 13, vertical: 12),
                  decoration: AppTheme.panel(radius: 14),
                  child: Row(
                    children: [
                      Icon(s['icon'] as IconData,
                          size: 21, color: AppColors.danger),
                      const SizedBox(width: 11),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(s['name'] as String,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style:
                                AppTheme.body(13, weight: FontWeight.w600)),
                            const SizedBox(height: 2),
                            Text(s['number'] as String,
                                style:
                                AppTheme.data(15, color: AppColors.danger)),
                          ],
                        ),
                      ),
                      const Icon(Icons.call, size: 16, color: AppColors.muted),
                    ],
                  ),
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 28),

        SectionHeader(
          _loadingGuardians
              ? 'Guardians'
              : '${_guardians.length} guardian${_guardians.length == 1 ? '' : 's'}',
          trailing: GestureDetector(
            onTap: () => Navigator.pushNamed(context, '/guardians')
                .then((_) => _loadGuardians()),
            child: Text('Manage', style: AppTheme.eyebrow(color: AppColors.safe)),
          ),
        ),

        if (_loadingGuardians)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 20),
            child: Center(
                child: CircularProgressIndicator(
                    color: AppColors.safe, strokeWidth: 2.5)),
          )
        else if (_guardians.isEmpty)
          Container(
            padding: const EdgeInsets.all(18),
            decoration: AppTheme.panel(
                border: AppColors.caution.withValues(alpha: 0.4)),
            child: Column(
              children: [
                const Icon(Icons.person_off_outlined,
                    size: 26, color: AppColors.caution),
                const SizedBox(height: 12),
                Text('No guardians yet',
                    style: AppTheme.body(14.5, weight: FontWeight.w600)),
                const SizedBox(height: 6),
                Text(
                  'An SOS will be recorded, but nobody will be notified until you add someone.',
                  textAlign: TextAlign.center,
                  style: AppTheme.body(12.5, color: AppColors.muted),
                ),
                const SizedBox(height: 16),
                AppButton(
                  label: 'Add a guardian',
                  outlined: true,
                  onPressed: () => Navigator.pushNamed(context, '/guardians')
                      .then((_) => _loadGuardians()),
                ),
              ],
            ),
          )
        else
          ..._guardians.map((g) => Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(14),
            decoration: AppTheme.panel(),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 21,
                  backgroundColor: AppColors.asphalt600,
                  child: Text((g['name'] as String)[0].toUpperCase(),
                      style:
                      AppTheme.display(16, weight: FontWeight.w700)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(g['name'] as String,
                          style:
                          AppTheme.body(15, weight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      Text('${g['relation']} · ${g['phone']}',
                          style: AppTheme.body(12.5,
                              color: AppColors.muted)),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: () => _dial(g['phone'] as String),
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.call,
                      size: 19, color: AppColors.safe),
                ),
              ],
            ),
          )),
      ],
    );

    if (widget.embedded) return content;

    return Scaffold(
      appBar: AppBar(title: const Text('SOS')),
      body: SafeArea(child: content),
    );
  }

  Widget _buildTrigger() {
    final sent = _activeAlert != null;
    final color = sent
        ? AppColors.safe
        : _counting
        ? AppColors.caution
        : AppColors.danger;

    return GestureDetector(
      onLongPress: (_counting || sent || _sending) ? null : _beginCountdown,
      onTap: () {
        if (_counting) {
          _cancelCountdown();
        } else if (!sent && !_sending) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Press and hold to send an SOS.')),
          );
        }
      },
      child: AnimatedBuilder(
        animation: _pulse,
        builder: (_, child) {
          final t = _counting ? _pulse.value : _pulse.value * 0.5;
          return Container(
            width: 210,
            height: 210,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.09 + t * 0.06),
              border: Border.all(
                  color: color.withValues(alpha: 0.3 + t * 0.35), width: 2),
            ),
            child: Center(child: child),
          );
        },
        child: Container(
          width: 150,
          height: 150,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color,
            boxShadow: [
              BoxShadow(color: color.withValues(alpha: 0.4), blurRadius: 28),
            ],
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (_sending) ...[
                const SizedBox(
                  width: 34,
                  height: 34,
                  child: CircularProgressIndicator(
                      color: AppColors.asphalt900, strokeWidth: 3),
                ),
                const SizedBox(height: 10),
                Text('SENDING',
                    style: AppTheme.eyebrow(color: AppColors.asphalt900)),
              ] else if (_counting) ...[
                Text('$_seconds',
                    style: AppTheme.data(50,
                        weight: FontWeight.w800, color: AppColors.asphalt900)),
                Text('TAP TO CANCEL',
                    style: AppTheme.eyebrow(color: AppColors.asphalt900)),
              ] else if (sent) ...[
                const Icon(Icons.check, size: 46, color: AppColors.asphalt900),
                const SizedBox(height: 4),
                Text('ALERT SENT',
                    style: AppTheme.eyebrow(color: AppColors.asphalt900)),
              ] else ...[
                Text('SOS',
                    style: AppTheme.display(34,
                        weight: FontWeight.w900,
                        spacing: 3,
                        color: AppColors.asphalt900)),
                const SizedBox(height: 2),
                Text('HOLD',
                    style: AppTheme.eyebrow(color: AppColors.asphalt900)),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildIdleHint() {
    return Center(
      child: SizedBox(
        width: 270,
        child: Text(
          _counting
              ? 'Sending your location to all guardians. Tap the button to stop.'
              : 'Press and hold for a second. You get five seconds to cancel before anyone is alerted.',
          textAlign: TextAlign.center,
          style: AppTheme.body(13.5, color: AppColors.muted),
        ),
      ),
    );
  }

  Widget _buildSentPanel() {
    final alert = _activeAlert!;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: AppTheme.panel(border: AppColors.safe.withValues(alpha: 0.4)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.podcasts, size: 19, color: AppColors.safe),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _notifiedCount > 0
                      ? '$_notifiedCount guardian${_notifiedCount == 1 ? '' : 's'} notified'
                      : 'Alert recorded',
                  style: AppTheme.body(14.5, weight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            alert['place_name'] != null
                ? 'Live location shared: ${alert['place_name']}'
                : 'Live location shared',
            style: AppTheme.body(12.5, color: AppColors.muted),
          ),
          const SizedBox(height: 4),
          Text('Your position updates every 12 seconds while this is open.',
              style: AppTheme.body(11.5, color: AppColors.faint)),

          if (_notifiedCount == 0 && _guardians.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'None of your guardians have MARG open on their phone, so no push was delivered. Call them directly below.',
              style: AppTheme.body(12.5, color: AppColors.caution),
            ),
          ],

          const SizedBox(height: 14),
          const LaneDivider(dashWidth: 8, gap: 6),
          const SizedBox(height: 14),

          ..._guardians.map((g) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                Icon(
                  g['has_app'] == true
                      ? Icons.check_circle
                      : Icons.remove_circle_outline,
                  size: 15,
                  color: g['has_app'] == true
                      ? AppColors.safe
                      : AppColors.muted,
                ),
                const SizedBox(width: 10),
                Text(g['name'] as String, style: AppTheme.body(13.5)),
                const Spacer(),
                Text(
                  g['has_app'] == true ? 'Notified' : 'No app — call them',
                  style: AppTheme.body(12.5, color: AppColors.muted),
                ),
              ],
            ),
          )),

          const SizedBox(height: 10),
          AppButton(
            label: "I'm safe — stand down",
            color: AppColors.safe,
            outlined: true,
            loading: _sending,
            onPressed: _standDown,
          ),
        ],
      ),
    );
  }
}
