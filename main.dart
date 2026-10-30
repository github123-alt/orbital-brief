import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// TODO: put your Render URL here (no trailing slash), e.g.
/// 'https://orbital-brief.onrender.com'
const String kApiBase = 'https://YOUR-SERVICE.onrender.com';

const String _kCacheKey = 'briefing_cache_v1';

// Render's free tier sleeps when idle; the first request can take ~a minute.
const Duration _kRequestTimeout = Duration(seconds: 90);

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

/// Splits the plain-text briefing into tiles. A section starts at an
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
// UI
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
    });
    try {
      final fresh = await fetchBriefing(forceRefresh: force);
      await saveCache(fresh);
      if (!mounted) return;
      setState(() => _briefing = fresh);
    } on TimeoutException {
      if (!mounted) return;
      setState(() => _error = 'The server took too long to respond.');
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not reach the server.');
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
    final b = _briefing;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Orbital Brief'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : () => _refresh(),
          ),
        ],
      ),
      body: _buildBody(b),
    );
  }

  Widget _buildBody(Briefing? b) {
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
                  'Contacting the Orbital Brief server…\n'
                  'The first load after a quiet period can take up to a minute.',
                  textAlign: TextAlign.center,
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
              const Icon(Icons.cloud_off, size: 48),
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
    return RefreshIndicator(
      onRefresh: () => _refresh(),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        children: [
          if (_loading) const LinearProgressIndicator(),
          if (_error != null)
            _Banner(
              icon: Icons.wifi_off,
              text: '$_error Showing the briefing saved ${_stamp(b.savedAt)}.',
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
            child: Text(
              'Daily Space Operations Briefing — ${b.date}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          if (parsed.summary.isNotEmpty)
            _TileCard(
              title: 'SUMMARY',
              body: parsed.summary,
              color: Colors.redAccent,
            ),
          for (final s in parsed.sections)
            _TileCard(
              title: s.title,
              body: s.body,
              color: _colorFor(s.title, s.body),
            ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

Color _colorFor(String title, String body) {
  if (body.contains('temporarily unavailable') ||
      body.contains('Unavailable')) {
    return Colors.grey;
  }
  final t = title.toUpperCase();
  if (t.contains('FLARE')) return Colors.orange;
  if (t.contains('GEOMAGNETIC')) return Colors.purpleAccent;
  if (t.contains('NEAR-EARTH')) return Colors.amber;
  if (t.contains('EARTH EVENTS')) return Colors.green;
  if (t.contains('STARLINK')) return Colors.indigoAccent;
  if (t.contains('SATELLITES')) return Colors.blue;
  if (t.contains('SPACECRAFT')) return Colors.teal;
  if (t.contains('MISSION')) return Colors.cyan;
  if (t.contains('DEEP')) return Colors.deepPurpleAccent;
  if (t.contains('LUNAR')) return Colors.blueGrey;
  return Colors.lightBlueAccent;
}

class _TileCard extends StatelessWidget {
  final String title;
  final String body;
  final Color color;

  const _TileCard({
    required this.title,
    required this.body,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: color, width: 5)),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
          SelectableText(body, style: const TextStyle(height: 1.4)),
        ],
      ),
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
        color: Colors.orange.withAlpha(40),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}
