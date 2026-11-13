#!/usr/bin/env python3
"""Compile actual size/placement bodies against real Qt widgets, without the app.

This exercises both leaf orientations and split aggregation; it does not replace
interactive drag, saved-room or native-window-manager acceptance testing.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'toonz/sources/toonzqt/docklayout.cpp'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


FIXTURE = r'''
#include <QApplication>
#include <QWidget>
#include <QRectF>
#include <QPoint>
#include <algorithm>
#include <deque>
#include <vector>
#include <iostream>
#include <stdexcept>
class Region;
class DockLayout;
class DockWidget : public QWidget { public: using QWidget::QWidget; };
class DockSeparator : public QWidget { public: int m_index = 0; };
class DockLayout {
public:
 std::deque<Region *> m_regions;
 DockWidget *m_maximizedDock = nullptr;
 QWidget *m_tabMergePreview = nullptr;
 Region *m_tabMergeTargetRegion = nullptr;
 int tabStripHeight() const { return 26; }
 int spacing() const { return 4; }
 void updateSeparatorCursors() {}
 void updateTabMergePreviewGeometry() {}
 void applyGeometry();
};
class Region {
public:
 enum { horizontal=0, vertical=1 };
 DockLayout *m_owner;
 DockWidget *m_item=nullptr;
 std::vector<DockWidget *> m_tabItems;
 std::deque<Region *> m_childList;
 std::deque<DockSeparator *> m_separators;
 int m_minimumSize[2] = {0,0}, m_maximumSize[2] = {0,0};
 bool m_orientation=false;
 QRectF rect;
 QWidget *strip=nullptr;
 Region(DockLayout *owner):m_owner(owner){}
 bool hasTabGroup() const { return m_tabItems.size()>1; }
 bool getOrientation() const { return m_orientation; }
 DockWidget *getItem() const { return m_item; }
 DockWidget *activeTab() const { return m_tabItems.front(); }
 const std::vector<DockWidget *> &tabItems() const { return m_tabItems; }
 QWidget *tabStripContainer() const { return strip; }
 QRectF getGeometry() const { return rect; }
 const std::deque<Region *> &getChildList() const { return m_childList; }
 std::deque<DockSeparator *> &separators() { return m_separators; }
 int getMinimumSize(bool direction) const { return m_minimumSize[direction]; }
 int getMaximumSize(bool direction) const { return m_maximumSize[direction]; }
 int calculateMinimumSize(bool direction,bool recalcChildren);
 int calculateMaximumSize(bool direction,bool recalcChildren);
};
void check(bool ok, const char *message) {
 if (!ok) throw std::runtime_error(message);
}
'''

MAIN = r'''
int main(int argc,char **argv) {
 QApplication app(argc,argv);
 for (bool orientation : {false,true}) {
  DockLayout layout;
  Region group(&layout);
  group.m_orientation=orientation;
  DockWidget a,b;
  a.setMinimumSize(80,100); a.setMaximumSize(500,400);
  b.setMinimumSize(100,120); b.setMaximumSize(450,350);
  group.m_tabItems={&a,&b}; group.m_item=&a;
  QWidget strip; group.strip=&strip;
  layout.m_regions.push_back(&group);
  check(group.calculateMinimumSize(Region::horizontal,true)==100,"tab min width");
  check(group.calculateMaximumSize(Region::horizontal,true)==450,"tab max width");
  int minHeight=group.calculateMinimumSize(Region::vertical,true);
  int maxHeight=group.calculateMaximumSize(Region::vertical,true);
  check(minHeight==146,"tab min height must include strip in both orientations");
  check(maxHeight==376,"tab max height must include strip in both orientations");
  group.rect=QRectF(0,0,100,minHeight);
  layout.applyGeometry();
  check(a.geometry().height()==120,"minimum allocation preserves content minimum");
  check(b.geometry()==a.geometry(),"inactive member keeps content geometry");
  check(strip.geometry().height()==26,"actual placement reserves strip height");
  group.rect=QRectF(0,0,450,maxHeight);
  layout.applyGeometry();
  check(a.geometry().height()==350,"maximum allocation preserves shared maximum");
  // Ordinary leaves must preserve their existing orientation-independent bounds.
  Region single(&layout); single.m_orientation=orientation; single.m_item=&b;
  check(single.calculateMinimumSize(0,true)==100,"single min width");
  check(single.calculateMinimumSize(1,true)==120,"single min height");
  check(single.calculateMaximumSize(0,true)==450,"single max width");
  check(single.calculateMaximumSize(1,true)==350,"single max height");
  // Verify actual recursive aggregation includes the tab strip exactly once.
  DockWidget c; c.setMinimumSize(50,90); c.setMaximumSize(300,500);
  Region other(&layout); other.m_item=&c;
  Region parent(&layout); parent.m_orientation=orientation;
  parent.m_childList={&group,&other};
  DockSeparator separator; parent.m_separators.push_back(&separator);
  check(parent.calculateMinimumSize(0,true)==(orientation?100:154),"split min width");
  check(parent.calculateMinimumSize(1,true)==(orientation?240:146),"split min height");
  check(parent.calculateMaximumSize(0,true)==(orientation?300:754),"split max width");
  check(parent.calculateMaximumSize(1,true)==(orientation?880:376),"split max height");
 }
 std::cout << "PASS: both orientations, actual min/max and applyGeometry, single and split bounds\n";
}
'''


def main():
    source = SOURCE.read_text()
    bodies = '\n'.join(function(source, signature) for signature in (
        'inline QRect toRect(', 'void DockLayout::applyGeometry()',
        'int Region::calculateMinimumSize(', 'int Region::calculateMaximumSize('))
    flags = shlex.split(subprocess.check_output(
        ['pkg-config', '--cflags', '--libs', 'Qt5Widgets'], text=True))
    with tempfile.TemporaryDirectory(prefix='dock-tab-geometry-') as directory:
        cpp, executable = Path(directory)/'test.cpp', Path(directory)/'test'
        cpp.write_text(FIXTURE + '\n' + bodies + '\n' + MAIN)
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-fPIC',
                        str(cpp), '-o', str(executable), *flags], check=True)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
        subprocess.run([str(executable)], env=env, check=True, timeout=30)


if __name__ == '__main__':
    main()
