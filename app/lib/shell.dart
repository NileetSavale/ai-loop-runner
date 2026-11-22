import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'screens/sessions_screen.dart';

/// Wide enough for a sidebar and two panes.
const wideLayout = 900.0;

const _sections = [
  (path: '/sessions', label: 'Sessions', icon: Icons.play_circle_outline, selectedIcon: Icons.play_circle),
  (path: '/pipelines', label: 'Pipelines', icon: Icons.account_tree_outlined, selectedIcon: Icons.account_tree),
  (path: '/keys', label: 'API keys', icon: Icons.key_outlined, selectedIcon: Icons.key),
];

bool get _isMac => !kIsWeb && defaultTargetPlatform == TargetPlatform.macOS;

/// The frame around every signed-in screen: a sidebar on a wide window, a bottom bar on a narrow one, and the
/// menu bar and shortcuts (Cmd on macOS, Ctrl elsewhere): New session, Refresh, and one per section.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.location, required this.child});
  final String location;
  final Widget child;

  int get _selected {
    final index = _sections.indexWhere((s) => location.startsWith(s.path));
    return index < 0 ? 0 : index;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    void newSession() => context.go('/sessions/new');
    void refresh() => ref.invalidate(sessionsProvider);
    void open(int i) => context.go(_sections[i].path);

    final wide = MediaQuery.sizeOf(context).width >= wideLayout;
    final body = wide
        ? Row(
            children: [
              NavigationRail(
                selectedIndex: _selected,
                labelType: NavigationRailLabelType.all,
                onDestinationSelected: open,
                leading: Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: FloatingActionButton.small(
                    tooltip: 'New session',
                    elevation: 0,
                    onPressed: newSession,
                    child: const Icon(Icons.add),
                  ),
                ),
                destinations: [
                  for (final s in _sections)
                    NavigationRailDestination(
                      icon: Icon(s.icon),
                      selectedIcon: Icon(s.selectedIcon),
                      label: Text(s.label),
                    ),
                ],
              ),
              const VerticalDivider(width: 1),
              Expanded(child: child),
            ],
          )
        : Scaffold(
            body: child,
            bottomNavigationBar: NavigationBar(
              selectedIndex: _selected,
              onDestinationSelected: open,
              destinations: [
                for (final s in _sections)
                  NavigationDestination(icon: Icon(s.icon), selectedIcon: Icon(s.selectedIcon), label: s.label),
              ],
            ),
          );

    // macOS draws the menu bar and handles its shortcuts itself; elsewhere the same shortcuts use Ctrl
    if (_isMac) {
      return PlatformMenuBar(
        menus: [
          const PlatformMenu(
            label: 'Loop Runner',
            menus: [
              PlatformMenuItemGroup(members: [PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.about)]),
              PlatformMenuItemGroup(members: [PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.quit)]),
            ],
          ),
          PlatformMenu(
            label: 'File',
            menus: [
              PlatformMenuItem(
                label: 'New session',
                shortcut: const SingleActivator(LogicalKeyboardKey.keyN, meta: true),
                onSelected: newSession,
              ),
            ],
          ),
          PlatformMenu(
            label: 'View',
            menus: [
              PlatformMenuItem(
                label: 'Refresh',
                shortcut: const SingleActivator(LogicalKeyboardKey.keyR, meta: true),
                onSelected: refresh,
              ),
              PlatformMenuItemGroup(
                members: [
                  for (final (i, s) in _sections.indexed)
                    PlatformMenuItem(
                      label: s.label,
                      shortcut: SingleActivator(LogicalKeyboardKey(LogicalKeyboardKey.digit1.keyId + i), meta: true),
                      onSelected: () => open(i),
                    ),
                ],
              ),
            ],
          ),
          const PlatformMenu(
            label: 'Window',
            menus: [
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.minimizeWindow),
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.zoomWindow),
            ],
          ),
        ],
        child: body,
      );
    }
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyN, control: true): newSession,
        const SingleActivator(LogicalKeyboardKey.keyR, control: true): refresh,
        for (final (i, _) in _sections.indexed)
          SingleActivator(LogicalKeyboardKey(LogicalKeyboardKey.digit1.keyId + i), control: true): () => open(i),
      },
      child: Focus(autofocus: true, child: body),
    );
  }
}
