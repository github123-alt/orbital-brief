import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

const String kApiBase = 'https://orbital-brief.onrender.com';

const String _kCacheKey = 'briefing_cache_v1';

// Render's free tier sleeps when idle (about a minute to wake), and /briefing
// then builds the whole briefing live, so allow plenty of time.
const Duration _kRequestTimeout = Duration(seconds: 150);

// The archive endpoints just read a file, so they are quick once awake.
const Duration _kArchiveTimeout = Duration(seconds: 90);

// Palette
const Color _kBg = Color(0xFF070B1A);
const Color _kBgTop = Color(0xFF0E1740);
const Color _kCard = Color(0xFF111830);
const Color _kOk = Color(0xFF2ECC71);
const Color _kWatch = Color(0xFFFFB020);
const Color _kAlert = Color(0xFFFF4D5E);
const Color _kMuted = Color(0xFF8892A6);

void main() => runApp(const OrbitalBriefApp());

class OrbitalBriefApp extends StatelessWidget {
  const OrbitalBriefApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Orbital Brief',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFF3D5AFE),
        scaffoldBackgroundColor: _kBg,
      ),
      home: const BriefingScreen(),
    );
  }
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

class Briefing {
  final String date;
  final String text;
  final DateTime savedAt;

  const Briefing({
    required this.date,
    required this.text,
    required this.savedAt,
  });

  Map<String, dynamic> toJson() => {
        'date': date,
        'briefing': text,
        'saved_at': savedAt.toIso8601String(),
      };

  factory Briefing.fromJson(Map<String, dynamic> j) => Briefing(
        date: j['date'] as String,
        text: j['briefing'] as String,
        savedAt: DateTime.tryParse((j['saved_at'] as String?) ?? '') ??
            DateTime.now(),
      );
}

class Section {
  final String title;
  final String body;
  const Section(this.title, this.body);
}

class ParsedBriefing {
  /// Alert banner + AI narrative (everything above "DETAILED DATA").
  final String summary;
  final List<Section> sections;
  const ParsedBriefing(this.summary, this.sections);
}

/// Splits the plain-text briefing into sections. A section starts at an
/// unindented line ("TITLE: text") and continues over indented and blank
/// lines, which is how briefing.py lays its sections out.
ParsedBriefing parseBriefing(String text) {
  const marker = '--- DETAILED DATA ---';
  final idx = text.indexOf(marker);

  final summary = (idx == -1 ? '' : text.substring(0, idx))
      .split('\n')
      .where((l) => !l.trim().startsWith('==='))
      .join('\n')
      .trim();
  final detail = idx == -1 ? text : text.substring(idx + marker.length);

  final sections = <Section>[];
  String? title;
  final body = StringBuffer();

  void flush() {
    if (title != null) {
      sections.add(Section(title!, body.toString().trim()));
    }
    body.clear();
    title = null;
  }

  for (final line in const LineSplitter().convert(detail)) {
    if (line.trim().isEmpty) {
      if (title != null) body.writeln();
      continue;
    }
    final indented = line.startsWith(' ') || line.startsWith('\t');
    if (!indented) {
      flush();
      final colon = line.indexOf(':');
      if (colon > 0 && colon < 70) {
        title = line.substring(0, colon).trim();
        body.writeln(line.substring(colon + 1).trim());
      } else {
        title = line.trim();
      }
    } else {
      body.writeln(line.trimRight());
    }
  }
  flush();

  return ParsedBriefing(summary, sections);
}

// ---------------------------------------------------------------------------
// Turning text sections into glanceable tiles
// ---------------------------------------------------------------------------

enum Level { ok, watch, alert, unavailable }

Color levelColor(Level l) {
  switch (l) {
    case Level.ok:
      return _kOk;
    case Level.watch:
      return _kWatch;
    case Level.alert:
      return _kAlert;
    case Level.unavailable:
      return _kMuted;
  }
}

int _levelRank(Level l) {
  switch (l) {
    case Level.alert:
      return 3;
    case Level.watch:
      return 2;
    case Level.ok:
      return 1;
    case Level.unavailable:
      return 0;
  }
}

class TileData {
  final int order;
  final String kind;
  final String label;
  final IconData icon;
  final String headline;
  final String sub;
  final Level level;
  final String body;
  final List<double>? bars; // 0..1, one per orbit regime
  final List<String>? barLabels;
  final List<Level>? dots; // one per mission operation

  const TileData({
    required this.order,
    required this.kind,
    required this.label,
    required this.icon,
    required this.headline,
    required this.sub,
    required this.level,
    required this.body,
    this.bars,
    this.barLabels,
    this.dots,
  });
}

class _Spec {
  final String kind;
  final String label;
  final IconData icon;
  const _Spec(this.kind, this.label, this.icon);
}

_Spec _specFor(String t) {
  if (t.contains('FLARE')) {
    return const _Spec('flare', 'Solar flares', Icons.wb_sunny);
  }
  if (t.contains('GEOMAGNETIC')) {
    return const _Spec('geo', 'Geomagnetic', Icons.bolt);
  }
  if (t.contains('NEAR-EARTH')) {
    return const _Spec('neo', 'Asteroids', Icons.travel_explore);
  }
  if (t.contains('EARTH EVENTS')) {
    return const _Spec('earth', 'Earth events', Icons.public);
  }
  if (t.contains('STARLINK')) {
    return const _Spec('starlink', 'Starlink', Icons.cell_tower);
  }
  if (t.contains('SATELLITES')) {
    return const _Spec('sats', 'Satellites', Icons.satellite_alt);
  }
  if (t.contains('SPACECRAFT')) {
    return const _Spec('health', 'Spacecraft health', Icons.monitor_heart);
  }
  if (t.contains('MISSION')) {
    return const _Spec('mission', 'Mission windows', Icons.task_alt);
  }
  if (t.contains('DEEP')) {
    return const _Spec('deep', 'Deep space', Icons.auto_awesome);
  }
  if (t.contains('LUNAR')) {
    return const _Spec('lunar', 'Lunar debris', Icons.nightlight_round);
  }
  return const _Spec('other', 'Details', Icons.info_outline);
}

int? _intMatch(RegExp r, String s) {
  final m = r.firstMatch(s);
  if (m == null) return null;
  return int.tryParse(m.group(1)!.replaceAll(',', ''));
}

String? _firstNumber(String s) {
  final m = RegExp(r'\d[\d,]*').firstMatch(s);
  return m?.group(0);
}

Level _scaleLevel(RegExp r, String body) {
  var max = 0;
  for (final m in r.allMatches(body)) {
    final v = int.tryParse(m.group(1)!) ?? 0;
    if (v > max) max = v;
  }
  if (max >= 3) return Level.alert;
  if (max >= 1) return Level.watch;
  return Level.ok;
}

Level _scoreLevel(int score) {
  if (score >= 60) return Level.alert;
  if (score >= 35) return Level.watch;
  return Level.ok;
}

TileData buildTile(Section s, int order) {
  final spec = _specFor(s.title.toUpperCase());
  final body = s.body;
  final unavailable = body.toLowerCase().contains('unavailable');

  var headline = '—';
  var sub = '';
  var level = Level.ok;
  List<double>? bars;
  List<String>? barLabels;
  List<Level>? dots;

  if (unavailable) {
    headline = 'Offline';
    sub = 'Temporarily unavailable';
    level = Level.unavailable;
  } else {
    switch (spec.kind) {
      case 'flare':
        final quiet =
            body.contains('Conditions quiet') || body.contains('No significant');
        final cls =
            RegExp(r'Most significant:\s*([A-Z][0-9.]*)').firstMatch(body)?.group(1);
        final n = _intMatch(RegExp(r'(\d+)\s+flare'), body);
        headline = quiet ? 'Quiet' : (cls ?? '—');
        sub = quiet ? 'No flares this week' : '${n ?? '?'} flares · 7 days';
        level = _scaleLevel(RegExp(r'\bR(\d)\b'), body);
        break;

      case 'geo':
        final quiet = body.contains('Conditions quiet');
        var maxG = -1;
        for (final m in RegExp(r'\bG(\d)\b').allMatches(body)) {
          final v = int.parse(m.group(1)!);
          if (v > maxG) maxG = v;
        }
        final n = _intMatch(RegExp(r'(\d+)\s+storm'), body);
        headline = quiet ? 'Quiet' : (maxG >= 0 ? 'G$maxG' : '—');
        sub = quiet ? 'No storms this week' : '${n ?? '?'} storms · 7 days';
        level = _scaleLevel(RegExp(r'\bG(\d)\b'), body);
        break;

      case 'neo':
        final n = _intMatch(RegExp(r'(\d+)\s+object'), body);
        headline = '${n ?? 0}';
        sub = 'close approaches';
        if (body.contains('Extremely close')) {
          level = Level.alert;
        } else if (body.contains('Very close') ||
            body.contains('Notable') ||
            body.contains('potentially-hazardous')) {
          level = Level.watch;
        }
        break;

      case 'sats':
        headline = _firstNumber(body) ?? '—';
        sub = 'tracked in orbit';
        break;

      case 'health':
        final scores = <int>[];
        barLabels = [];
        for (final m in RegExp(r'(LEO|MEO|GEO|HEO):\s*(\d+)/100').allMatches(body)) {
          barLabels.add(m.group(1)!);
          scores.add(int.parse(m.group(2)!));
        }
        if (scores.isNotEmpty) {
          final peak = scores.reduce(math.max);
          bars = scores.map((v) => (v / 100).clamp(0.08, 1.0)).toList();
          headline = '$peak';
          sub = 'peak risk / 100';
          level = _scoreLevel(peak);
        } else {
          barLabels = null;
        }
        break;

      case 'mission':
        final statuses = RegExp(r'\b(GO|CAUTION|HOLD)\b')
            .allMatches(body)
            .map((m) => m.group(1)!)
            .toList();
        if (statuses.isNotEmpty) {
          final go = statuses.where((x) => x == 'GO').length;
          final caution = statuses.where((x) => x == 'CAUTION').length;
          final hold = statuses.where((x) => x == 'HOLD').length;
          dots = statuses
              .map((x) => x == 'GO'
                  ? Level.ok
                  : (x == 'CAUTION' ? Level.watch : Level.alert))
              .toList();
          headline = '$go GO';
          sub = '$hold hold · $caution caution';
          level = hold > 0 ? Level.alert : (caution > 0 ? Level.watch : Level.ok);
        }
        break;

      case 'deep':
        final n = _intMatch(RegExp(r'(\d+)\s+tracked'), body);
        headline = n != null ? '$n' : (_firstNumber(body) ?? '—');
        sub = 'beyond Earth orbit';
        break;

      case 'lunar':
        final n = _intMatch(RegExp(r'(\d+)\s+object'), body);
        headline = n != null ? '$n' : (_firstNumber(body) ?? '—');
        sub = 'objects on the Moon';
        break;

      default: // earth, starlink, other
        headline = _firstNumber(body) ?? '—';
        sub = 'Tap for details';
    }
  }

  return TileData(
    order: order,
    kind: spec.kind,
    label: spec.label,
    icon: spec.icon,
    headline: headline,
    sub: sub,
    level: level,
    body: body,
    bars: bars,
    barLabels: barLabels,
    dots: dots,
  );
}

class HeroData {
  final bool allClear;
  final int alerts;
  final String? threat;
  final String narrative;
  final String full;
  const HeroData(this.allClear, this.alerts, this.threat, this.narrative, this.full);
}

HeroData parseHero(String summary) {
  final allClear = summary.contains('ALL CLEAR');
  final alerts =
      _intMatch(RegExp(r'ALERTS\s*\((\d+)\s+active\)'), summary) ?? 0;
  final threat =
      RegExp(r'THREAT LEVEL:\s*([A-Za-z]+)').firstMatch(summary)?.group(1);

  final narrative = summary
      .split('\n')
      .where((l) {
        final t = l.trim();
        if (t.isEmpty) return false;
        if (t.contains('OPERATIONAL STATUS')) return false;
        if (t.contains('OPERATIONAL ALERTS')) return false;
        if (t.contains('AI FLIGHT DIRECTOR')) return false;
        if (t.startsWith('•')) return false;
        return true;
      })
      .join(' ')
      .trim();

  return HeroData(allClear, alerts, threat, narrative, summary);
}

// ---------------------------------------------------------------------------
// Network + cache
// ---------------------------------------------------------------------------

Future<Briefing> fetchBriefing({bool forceRefresh = false}) async {
  final uri = Uri.parse('$kApiBase/briefing').replace(queryParameters: {
    'lang': 'en',
    if (forceRefresh) 'force_refresh': 'true',
  });
  final res = await http.get(uri).timeout(_kRequestTimeout);
  if (res.statusCode != 200) {
    throw Exception('Server returned ${res.statusCode}');
  }
  // Decode as UTF-8 explicitly so emoji and the long dash survive.
  final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
  return Briefing(
    date: data['date'] as String,
    text: data['briefing'] as String,
    savedAt: DateTime.now(),
  );
}

/// Newest briefing committed by the daily archive job. Much cheaper for the
/// server than generating a live one, so it works as a fallback.
Future<Briefing> fetchLatestArchived() async {
  final datesRes = await http
      .get(Uri.parse('$kApiBase/history/dates'))
      .timeout(_kArchiveTimeout);
  if (datesRes.statusCode != 200) {
    throw Exception('Server returned ${datesRes.statusCode}');
  }
  final dates = (jsonDecode(utf8.decode(datesRes.bodyBytes))
      as Map<String, dynamic>)['dates'] as List<dynamic>;
  if (dates.isEmpty) throw Exception('No archived briefings yet');

  final res = await http
      .get(Uri.parse('$kApiBase/history/${dates.first}'))
      .timeout(_kArchiveTimeout);
  if (res.statusCode != 200) {
    throw Exception('Server returned ${res.statusCode}');
  }
  final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
  return Briefing(
    date: data['date'] as String,
    text: data['briefing'] as String,
    savedAt: DateTime.now(),
  );
}

Future<void> saveCache(Briefing b) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString(_kCacheKey, jsonEncode(b.toJson()));
}

Future<Briefing?> loadCache() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kCacheKey);
    if (raw == null) return null;
    return Briefing.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  } catch (_) {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

class BriefingScreen extends StatefulWidget {
  const BriefingScreen({super.key});

  @override
  State<BriefingScreen> createState() => _BriefingScreenState();
}

class _BriefingScreenState extends State<BriefingScreen> {
  Briefing? _briefing;
  bool _loading = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final cached = await loadCache();
    if (!mounted) return;
    if (cached != null) setState(() => _briefing = cached);
    await _refresh();
  }

  Future<void> _refresh({bool force = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _notice = null;
    });
    try {
      final fresh = await fetchBriefing(forceRefresh: force);
      await saveCache(fresh);
      if (!mounted) return;
      setState(() => _briefing = fresh);
    } catch (e) {
      final reason = e is TimeoutException
          ? 'The live briefing is taking too long.'
          : 'Could not load the live briefing.';
      if (_briefing == null) {
        // Nothing saved on the phone yet: fall back to the newest archived
        // briefing so there is something to read.
        try {
          final archived = await fetchLatestArchived();
          await saveCache(archived);
          if (!mounted) return;
          setState(() {
            _briefing = archived;
            _notice = '$reason Showing the archived briefing for '
                '${archived.date}. Pull down to try the live one again.';
          });
        } catch (_) {
          if (!mounted) return;
          setState(() => _error = reason);
        }
      } else {
        if (!mounted) return;
        setState(() => _error = reason);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _stamp(DateTime t) {
    final d = t.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${d.year}-${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _kBg,
      body: Stack(
        children: [
          Positioned.fill(
            child: Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [_kBgTop, _kBg],
                  stops: [0.0, 0.55],
                ),
              ),
            ),
          ),
          const Positioned.fill(child: CustomPaint(painter: _StarPainter())),
          SafeArea(child: _buildContent(context)),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    final b = _briefing;

    if (b == null) {
      if (_loading) {
        return const Center(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 20),
                Text(
                  'Contacting mission control…\n'
                  'The first load after a quiet period can take a minute or two.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: _kMuted),
                ),
              ],
            ),
          ),
        );
      }
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 48, color: _kMuted),
              const SizedBox(height: 12),
              Text(_error ?? 'No briefing yet.', textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: () => _refresh(),
                child: const Text('Try again'),
              ),
            ],
          ),
        ),
      );
    }

    final parsed = parseBriefing(b.text);
    final hero = parseHero(parsed.summary);
    final tiles = <TileData>[
      for (var i = 0; i < parsed.sections.length; i++)
        buildTile(parsed.sections[i], i),
    ]..sort((a, c) {
        final r = _levelRank(c.level).compareTo(_levelRank(a.level));
        return r != 0 ? r : a.order.compareTo(c.order);
      });

    return RefreshIndicator(
      onRefresh: () => _refresh(),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(child: _buildHeader(b)),
          if (_notice != null || _error != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Column(
                  children: [
                    if (_notice != null)
                      _Banner(icon: Icons.history, text: _notice!),
                    if (_error != null)
                      _Banner(
                        icon: Icons.wifi_off,
                        text:
                            '$_error Showing the briefing saved ${_stamp(b.savedAt)}.',
                      ),
                  ],
                ),
              ),
            ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              child: _HeroCard(
                hero: hero,
                onTap: () => _openSheet(
                  context,
                  TileData(
                    order: -1,
                    kind: 'hero',
                    label: 'Flight director',
                    icon: Icons.auto_awesome,
                    headline: hero.allClear ? 'All clear' : '${hero.alerts} alerts',
                    sub: '',
                    level: hero.allClear ? Level.ok : Level.alert,
                    body: hero.full,
                  ),
                ),
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 0.9,
              ),
              delegate: SliverChildBuilderDelegate(
                (context, i) => _FadeIn(
                  index: i,
                  child: _Tile(
                    data: tiles[i],
                    onTap: () => _openSheet(context, tiles[i]),
                  ),
                ),
                childCount: tiles.length,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(Briefing b) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 8, 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'ORBITAL BRIEF',
                  style: TextStyle(
                    color: _kMuted,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 3,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  b.date,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(14),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          else
            IconButton(
              tooltip: 'Refresh',
              icon: const Icon(Icons.refresh),
              onPressed: () => _refresh(),
            ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Widgets
// ---------------------------------------------------------------------------

class _StarPainter extends CustomPainter {
  const _StarPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final rnd = math.Random(7);
    final paint = Paint();
    for (var i = 0; i < 90; i++) {
      final dx = rnd.nextDouble() * size.width;
      final dy = rnd.nextDouble() * size.height;
      final r = rnd.nextDouble() * 1.2 + 0.3;
      paint.color = Colors.white.withValues(alpha: rnd.nextDouble() * 0.5 + 0.1);
      canvas.drawCircle(Offset(dx, dy), r, paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _FadeIn extends StatelessWidget {
  final int index;
  final Widget child;
  const _FadeIn({required this.index, required this.child});

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: 1),
      duration: Duration(milliseconds: 350 + index * 70),
      curve: Curves.easeOutCubic,
      builder: (context, v, ch) => Opacity(
        opacity: v,
        child: Transform.translate(offset: Offset(0, 16 * (1 - v)), child: ch),
      ),
      child: child,
    );
  }
}

class _HeroCard extends StatelessWidget {
  final HeroData hero;
  final VoidCallback onTap;
  const _HeroCard({required this.hero, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = hero.allClear ? _kOk : _kAlert;
    final title = hero.allClear
        ? 'ALL CLEAR'
        : '${hero.alerts} ${hero.alerts == 1 ? 'ALERT' : 'ALERTS'}';

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: onTap,
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                color.withValues(alpha: 0.28),
                _kCard,
              ],
            ),
            border: Border.all(color: color.withValues(alpha: 0.45)),
          ),
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 46,
                    height: 46,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color.withValues(alpha: 0.2),
                    ),
                    child: Icon(
                      hero.allClear ? Icons.check_rounded : Icons.warning_amber_rounded,
                      color: color,
                      size: 28,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: TextStyle(
                            color: color,
                            fontSize: 24,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1,
                          ),
                        ),
                        const Text(
                          'OPERATIONAL STATUS',
                          style: TextStyle(
                            color: _kMuted,
                            fontSize: 11,
                            letterSpacing: 2,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (hero.threat != null)
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: color.withValues(alpha: 0.6)),
                      ),
                      child: Text(
                        hero.threat!.toUpperCase(),
                        style: TextStyle(
                          color: color,
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1,
                        ),
                      ),
                    ),
                ],
              ),
              if (hero.narrative.isNotEmpty) ...[
                const SizedBox(height: 14),
                Text(
                  hero.narrative,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(height: 1.4, color: Color(0xFFD5DAE8)),
                ),
                const SizedBox(height: 6),
                Text(
                  'Tap to read more',
                  style: TextStyle(
                    color: color,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  final TileData data;
  final VoidCallback onTap;
  const _Tile({required this.data, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = levelColor(data.level);
    return Material(
      color: _kCard,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: color.withValues(alpha: 0.28)),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color.withValues(alpha: 0.16),
                    ),
                    child: Icon(data.icon, color: color, size: 20),
                  ),
                  const Spacer(),
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color,
                      boxShadow: [
                        BoxShadow(
                          color: color.withValues(alpha: 0.6),
                          blurRadius: 8,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const Spacer(),
              Text(
                data.label.toUpperCase(),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: _kMuted,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 2),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  data.headline,
                  maxLines: 1,
                  style: TextStyle(
                    color: color,
                    fontSize: 32,
                    fontWeight: FontWeight.w900,
                    height: 1.1,
                  ),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                data.sub,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: _kMuted, fontSize: 12),
              ),
              if (data.bars != null) ...[
                const SizedBox(height: 8),
                SizedBox(height: 18, child: _MiniBars(data: data)),
              ] else if (data.dots != null) ...[
                const SizedBox(height: 8),
                SizedBox(height: 18, child: _MiniDots(dots: data.dots!)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _MiniBars extends StatelessWidget {
  final TileData data;
  const _MiniBars({required this.data});

  @override
  Widget build(BuildContext context) {
    final bars = data.bars!;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final v in bars)
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: Align(
                alignment: Alignment.bottomCenter,
                child: FractionallySizedBox(
                  heightFactor: v,
                  widthFactor: 1,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: levelColor(_scoreLevel((v * 100).round())),
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _MiniDots extends StatelessWidget {
  final List<Level> dots;
  const _MiniDots({required this.dots});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        for (final l in dots)
          Container(
            width: 12,
            height: 12,
            margin: const EdgeInsets.only(right: 6),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: levelColor(l),
            ),
          ),
      ],
    );
  }
}

class _Banner extends StatelessWidget {
  final IconData icon;
  final String text;
  const _Banner({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _kWatch.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _kWatch.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: _kWatch),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Detail sheet
// ---------------------------------------------------------------------------

void _openSheet(BuildContext context, TileData d) {
  final color = levelColor(d.level);
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: _kCard,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
    ),
    builder: (ctx) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.62,
      minChildSize: 0.35,
      maxChildSize: 0.94,
      builder: (ctx, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(22, 12, 22, 32),
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white24,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color.withValues(alpha: 0.18),
                ),
                child: Icon(d.icon, color: color),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      d.label.toUpperCase(),
                      style: const TextStyle(
                        color: _kMuted,
                        fontSize: 12,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      d.headline,
                      style: TextStyle(
                        color: color,
                        fontSize: 30,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (d.bars != null && d.barLabels != null) ...[
            const SizedBox(height: 18),
            for (var i = 0; i < d.bars!.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(
                  children: [
                    SizedBox(
                      width: 44,
                      child: Text(
                        d.barLabels![i],
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                    Expanded(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: LinearProgressIndicator(
                          value: d.bars![i],
                          minHeight: 10,
                          color: levelColor(_scoreLevel((d.bars![i] * 100).round())),
                          backgroundColor: Colors.white10,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    SizedBox(
                      width: 34,
                      child: Text(
                        '${(d.bars![i] * 100).round()}',
                        textAlign: TextAlign.right,
                        style: const TextStyle(color: _kMuted),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          const SizedBox(height: 18),
          const Divider(color: Colors.white12),
          const SizedBox(height: 10),
          for (final raw in const LineSplitter().convert(d.body))
            if (raw.trim().isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: SelectableText(
                  raw.trim(),
                  style: const TextStyle(height: 1.5, color: Color(0xFFD5DAE8)),
                ),
              ),
        ],
      ),
    ),
  );
}
