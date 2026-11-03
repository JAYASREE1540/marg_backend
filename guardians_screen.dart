import 'package:flutter/material.dart';

import '../../core/app_theme.dart';
import '../../core/widgets/app_controls.dart';
import '../../core/widgets/lane_divider.dart';
import '../../services/api_service.dart';

class GuardiansScreen extends StatefulWidget {
  const GuardiansScreen({super.key});

  @override
  State<GuardiansScreen> createState() => _GuardiansScreenState();
}

class _GuardiansScreenState extends State<GuardiansScreen> {
  List<Map<String, dynamic>> _guardians = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await ApiService.getGuardians();
      if (!mounted) return;
      setState(() {
        _guardians = list;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.message;
      });
    }
  }

  void _openAddSheet() {
    final name = TextEditingController();
    final phone = TextEditingController();
    final relation = TextEditingController();
    var saving = false;
    String? sheetError;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
          child: Container(
            padding: const EdgeInsets.fromLTRB(24, 22, 24, 32),
            decoration: const BoxDecoration(
              color: AppColors.asphalt800,
              borderRadius: BorderRadius.vertical(top: Radius.circular(22)),
            ),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Container(
                      width: 42,
                      height: 4,
                      decoration: BoxDecoration(
                        color: AppColors.asphalt600,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 22),
                  Text('Add a guardian',
                      style: AppTheme.display(21, weight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text(
                    'They receive your live location the moment you trigger an SOS.',
                    style: AppTheme.body(13.5, color: AppColors.muted),
                  ),
                  const SizedBox(height: 22),
                  AppTextField(
                    label: 'Name',
                    hint: 'Who is this?',
                    controller: name,
                    icon: Icons.person_outline,
                  ),
                  const SizedBox(height: 16),
                  AppTextField(
                    label: 'Mobile number',
                    hint: '10-digit number',
                    controller: phone,
                    icon: Icons.phone_outlined,
                    keyboardType: TextInputType.phone,
                  ),
                  const SizedBox(height: 16),
                  AppTextField(
                    label: 'Relationship',
                    hint: 'Mother, friend, colleague…',
                    controller: relation,
                    icon: Icons.diversity_3_outlined,
                  ),
                  if (sheetError != null) ...[
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(13),
                      decoration: AppTheme.panel(
                          border: AppColors.danger.withValues(alpha: 0.5)),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline,
                              size: 17, color: AppColors.danger),
                          const SizedBox(width: 11),
                          Expanded(
                              child: Text(sheetError!,
                                  style: AppTheme.body(12.5))),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                  AppButton(
                    label: 'Add guardian',
                    loading: saving,
                    onPressed: () async {
                      if (name.text.trim().isEmpty || phone.text.trim().isEmpty) {
                        setSheet(() =>
                        sheetError = 'Name and number are both needed.');
                        return;
                      }

                      setSheet(() {
                        saving = true;
                        sheetError = null;
                      });

                      try {
                        await ApiService.addGuardian(
                          name: name.text.trim(),
                          phone: phone.text.trim(),
                          relation: relation.text.trim().isEmpty
                              ? 'Contact'
                              : relation.text.trim(),
                        );
                        if (ctx.mounted) Navigator.pop(ctx);
                        _load();
                      } on ApiException catch (e) {
                        setSheet(() {
                          saving = false;
                          sheetError = e.message;
                        });
                      }
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _remove(int index) async {
    final guardian = _guardians[index];

    // Optimistic removal — the list feels instant, and we put the row back
    // if the server rejects it.
    setState(() => _guardians.removeAt(index));

    try {
      await ApiService.deleteGuardian(guardian['id'] as int);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${guardian['name']} removed')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _guardians.insert(index, guardian));
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Guardians')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAddSheet,
        backgroundColor: AppColors.safe,
        foregroundColor: AppColors.asphalt900,
        icon: const Icon(Icons.person_add_alt),
        label: Text('Add',
            style: AppTheme.display(14,
                weight: FontWeight.w700, color: AppColors.asphalt900)),
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          color: AppColors.safe,
          backgroundColor: AppColors.asphalt800,
          child: _buildBody(),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
          child: CircularProgressIndicator(
              color: AppColors.safe, strokeWidth: 2.5));
    }

    if (_error != null) {
      return ListView(
        padding: const EdgeInsets.all(40),
        children: [
          const SizedBox(height: 60),
          const Icon(Icons.cloud_off, size: 42, color: AppColors.faint),
          const SizedBox(height: 18),
          Text(_error!,
              textAlign: TextAlign.center,
              style: AppTheme.body(13.5, color: AppColors.muted)),
          const SizedBox(height: 24),
          AppButton(label: 'Try again', onPressed: _load),
        ],
      );
    }

    if (_guardians.isEmpty) return _emptyState();

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 90),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration:
          AppTheme.panel(border: AppColors.safe.withValues(alpha: 0.28)),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.shield_outlined, size: 19, color: AppColors.safe),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Guardians who have MARG installed receive an instant push notification with your live location.',
                  style: AppTheme.body(13, color: AppColors.muted),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 26),
        SectionHeader('${_guardians.length} added'),
        ...List.generate(_guardians.length, (i) {
          final g = _guardians[i];
          final hasApp = g['has_app'] == true;

          return Dismissible(
            key: ValueKey(g['id']),
            direction: DismissDirection.endToStart,
            onDismissed: (_) => _remove(i),
            background: Container(
              alignment: Alignment.centerRight,
              padding: const EdgeInsets.only(right: 20),
              margin: const EdgeInsets.only(bottom: 10),
              decoration: BoxDecoration(
                color: AppColors.danger.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Icon(Icons.delete_outline, color: AppColors.danger),
            ),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(16),
              decoration: AppTheme.panel(),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 22,
                    backgroundColor: AppColors.asphalt600,
                    child: Text(
                      (g['name'] as String)[0].toUpperCase(),
                      style: AppTheme.display(17, weight: FontWeight.w700),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(g['name'] as String,
                            style:
                            AppTheme.body(15.5, weight: FontWeight.w600)),
                        const SizedBox(height: 3),
                        Text(g['relation'] as String,
                            style:
                            AppTheme.body(12.5, color: AppColors.muted)),
                        const SizedBox(height: 3),
                        Text(g['phone'] as String,
                            style: AppTheme.data(12.5, color: AppColors.muted)),
                      ],
                    ),
                  ),
                  StatusPill(
                    label: hasApp ? 'Push' : 'No app',
                    color: hasApp ? AppColors.safe : AppColors.muted,
                    icon: hasApp
                        ? Icons.notifications_active_outlined
                        : Icons.phone_outlined,
                  ),
                ],
              ),
            ),
          );
        }),
        const SizedBox(height: 18),
        Center(
          child: Text('Swipe a guardian left to remove',
              style: AppTheme.body(12.5, color: AppColors.faint)),
        ),
      ],
    );
  }

  Widget _emptyState() {
    return ListView(
      children: [
        const SizedBox(height: 100),
        Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            children: [
              const Icon(Icons.group_add_outlined,
                  size: 46, color: AppColors.faint),
              const SizedBox(height: 18),
              Text('No guardians yet',
                  style: AppTheme.display(19, weight: FontWeight.w700)),
              const SizedBox(height: 8),
              Text(
                'Add at least one person who should be told if something goes wrong on the road.',
                textAlign: TextAlign.center,
                style: AppTheme.body(13.5, color: AppColors.muted),
              ),
              const SizedBox(height: 24),
              AppButton(
                  label: 'Add your first guardian', onPressed: _openAddSheet),
            ],
          ),
        ),
      ],
    );
  }
}
