#!/usr/bin/env python3
"""Execute the actual TypeTool history-toggle branch with a bounded C++ harness.

No Qt application or provider is loaded. Stub collaborators model the transition
contract; native font geometry, actual preview and GUI interaction remain untested.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def actual_toggle_branch(source):
    start = source.index('bool TypeTool::onPropertyChanged(std::string propertyName) {')
    start = source.index('  if (propertyName == m_textHistoryEnabled.getName()) {', start)
    depth = 0
    for index in range(source.index('{', start), len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise ValueError('Unbalanced actual source branch')


HARNESS = r'''
#include <string>
#include <vector>
#include <iostream>
#include <cstdlib>
struct BoolProperty {
  bool value;
  std::string getName() { return "Text History"; }
  bool getValue() { return value; }
};
struct History {
  bool enabled = true;
  int loads = 0;
  void load() { ++loads; }
  void setEnabled(bool value) { enabled = value; }
};
struct Tool {
  BoolProperty m_textHistoryEnabled{false};
  History m_textHistory;
  bool m_formattedCacheValid = true, m_active = true, m_validFonts = true;
  int shown = 0, hidden = 0, invalidations = 0, cursor = 0;
  std::vector<int> positions{0, 0, 0};
  std::vector<std::string> calls;
  void showTextHistoryPopup() { ++shown; }
  void hideTextHistoryPopup() { ++hidden; }
  void updateCharPositions() {
    calls.push_back("positions");
    positions = {100, 110, 120};
  }
  void updateCursorPoint() {
    calls.push_back("cursor");
    cursor = positions.back() + 10;
  }
  void invalidate() { calls.push_back("invalidate"); ++invalidations; }
  bool onPropertyChanged(std::string propertyName) {
    ACTUAL_BRANCH
    return false;
  }
};
void require(bool value, const char *message) {
  if (!value) { std::cerr << message << '\n'; std::exit(1); }
}
int main() {
  // Active Markdown has bypassed per-character placement. Disable history
  // without any subsequent edit: placement must be refreshed immediately.
  for (bool enabled : {false, true}) {
    Tool tool;
    tool.m_textHistoryEnabled.value = enabled;
    require(tool.onPropertyChanged("Text History"), "Toggle not handled");
    require(tool.positions == std::vector<int>({100,110,120}),
            "Active transition left stale/default character positions");
    require(tool.cursor == 130, "Cursor not recomputed after positions");
    require(tool.calls == std::vector<std::string>({"positions","cursor","invalidate"}),
            "Placement/cursor/redraw ordering incorrect");
    require(!tool.m_formattedCacheValid, "Formatted cache not invalidated");
    require(tool.m_textHistory.loads == 1 && tool.m_textHistory.enabled == enabled,
            "History setting persistence changed");
    require(tool.shown == int(enabled) && tool.hidden == int(!enabled),
            "Popup behavior changed");
  }
  for (bool active : {false,true}) for (bool fonts : {false,true}) {
    if (active && fonts) continue;
    Tool tool;
    tool.m_active = active; tool.m_validFonts = fonts;
    require(tool.onPropertyChanged("Text History"), "Inactive toggle not handled");
    require(tool.calls.empty(), "Invalid/inactive text unexpectedly laid out");
    require(!tool.m_formattedCacheValid, "Inactive transition retained stale cache");
    require(tool.hidden == 1, "Inactive popup hiding changed");
  }
  Tool unrelated;
  require(!unrelated.onPropertyChanged("Other"), "Unrelated branch intercepted");
  require(unrelated.calls.empty() && unrelated.m_textHistory.loads == 0,
          "Unrelated property changed history");
  std::cout << "Actual TypeTool toggle branch: 6 transition boundaries passed\n";
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--compiler', default='c++')
    args = parser.parse_args()
    compiler = shutil.which(args.compiler)
    if compiler is None:
        raise SystemExit('C++ compiler required; regression must not silently skip')
    branch = actual_toggle_branch(args.source.read_text())
    with tempfile.TemporaryDirectory(prefix='type-history-transition-') as directory:
        directory = Path(directory)
        cpp = directory / 'transition.cpp'
        binary = directory / 'transition'
        cpp.write_text(HARNESS.replace('ACTUAL_BRANCH', branch))
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)], check=True, timeout=60)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    main()
