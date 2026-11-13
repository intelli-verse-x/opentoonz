#!/usr/bin/env python3
"""Actual tab mutation/event bodies compiled with real Qt, no application import.

Instrumented dependencies count mutation boundaries. This is a bounded policy
regression, not a substitute for interactive native window-manager testing.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


FIXTURE = r'''
#include <QApplication>
#include <QMouseEvent>
#include <QTabBar>
#include <QWidget>
#include <QVariant>
#include <algorithm>
#include <cmath>
#include <vector>
#include <stdexcept>
#include <iostream>
class DockLayout;
class DockingCheck {
public:
 bool enabled=false;
 static DockingCheck *instance() { static DockingCheck lock; return &lock; }
 bool isEnabled() const { return enabled; }
};
enum class StripDeletion { Immediate,Deferred };
enum class LayoutUpdate { Geometry,Full };
class DockWidget : public QWidget {
public:
 using QWidget::QWidget;
 enum { fixed=1 };
 bool m_undocking=false,m_dragging=false;
 QPoint m_dragMouseInitialPos,m_dragInitialPos;
 int getFixWidthMode() const { return 0; }
 QPoint settledDragGripOffset() { return {}; }
};
class Region {
public:
 std::vector<DockWidget *> tabs;
 int active=0, moved=0;
 bool hasTabGroup() const { return tabs.size()>1; }
 const std::vector<DockWidget *> &tabItems() const { return tabs; }
 int activeTabIndex() const { return active; }
 bool containsPanel(DockWidget *item) { return std::find(tabs.begin(),tabs.end(),item)!=tabs.end(); }
 void moveTab(int,int) { ++moved; }
 struct Strip { void syncFromRegion() {} } *m_tabStrip=nullptr;
};
class DockLayout {
public:
 DockWidget *m_maximizedDock=nullptr;
 QWidget parent;
 Region *targetRegion=nullptr;
 int detached=0,added=0,finished=0,activated=0,undocked=0;
 DockWidget *getMaximized() const { return m_maximizedDock; }
 QWidget *parentWidget() { return &parent; }
 Region *find(DockWidget *) { return targetRegion; }
 bool detachPanelFromCurrentRegion(DockWidget *,Region *) { ++detached; return true; }
 void addPanelToTabGroup(DockWidget *,Region *) { ++added; }
 void hideTabMergePreview() {}
 void finishLayoutChange(LayoutUpdate) { ++finished; }
 void setActiveTab(Region *,int) { ++activated; }
 void updateTabVisibility(Region *) {}
 bool undockFromTabGroup(DockWidget *,Region *,StripDeletion) { ++undocked; return false; }
 void calculateDockPlaceholders(DockWidget *) {}
 static bool supportsTabGrouping(const DockWidget *);
 bool canMergeAsTabs(DockWidget *,DockWidget *) const;
 void mergePanelsAsTabs(DockWidget *,DockWidget *);
 void reorderTab(Region *,int,int);
 bool detachTabForDrag(DockWidget *,Region *,const QPoint &,const QPoint &);
};
class DockTabStrip : public QTabBar {
public:
 DockLayout *m_layout;
 Region *m_region;
 int m_pressIndex=0;
 bool m_dragOutStarted=false,m_reordering=false;
 int m_insertionGapIndex=-1,mutationAttempts=0;
 QPoint m_pressPos,m_globalPressPos;
 static const int kUndockDragThreshold=8;
 DockTabStrip(DockLayout *layout,Region *region):m_layout(layout),m_region(region) {
  setMovable(false); addTab("A");addTab("B");resize(200,26);
 }
 void clearInsertionMarker() { m_insertionGapIndex=-1; }
 void setInsertionGapIndex(int gap) { m_insertionGapIndex=gap; }
 bool isOutsideTabStrip(const QPoint &) const { return false; }
 int insertionGapAt(const QPoint &) const { return 2; }
 // Instrument the dependency; the real mouse event body must not reach it
 // under a lock/maximized layout.
 void tryBeginDragOut(const QPoint &) { ++mutationAttempts; }
 void mouseMoveEvent(QMouseEvent *) override;
};
void check(bool ok,const char *message) { if(!ok) throw std::runtime_error(message); }
'''

MAIN = r'''
int main(int argc,char **argv) {
 QApplication app(argc,argv);
 for(int mode=0;mode<3;++mode) {
  DockLayout layout; DockWidget a,b,c; Region region;
  region.tabs={&b,&c}; layout.targetRegion=&region;
  DockingCheck::instance()->enabled=mode==1;
  if(mode==2) layout.m_maximizedDock=&c;
  const bool allowed=mode==0;
  check(layout.canMergeAsTabs(&a,&b)==allowed,"merge predicate lock/max gate");
  layout.mergePanelsAsTabs(&a,&b);
  check(layout.added==(allowed?1:0),"floating title-drop reaches no mutation while blocked");
  check(layout.detached==(allowed?1:0),"blocked merge must not detach source");
  layout.reorderTab(&region,0,1);
  check(region.moved==(allowed?1:0),"reorder policy");
  layout.detachTabForDrag(&b,&region,QPoint(1,1),QPoint());
  check(layout.undocked==(allowed?1:0),"drag-out must not call undocking while blocked");
  DockTabStrip strip(&layout,&region);
  strip.m_globalPressPos=QPoint(0,0); strip.m_pressIndex=0;
  strip.m_reordering=true;strip.m_insertionGapIndex=2;
  QMouseEvent event(QEvent::MouseMove,QPointF(2,20),QPointF(2,20),
                    Qt::NoButton,Qt::LeftButton,Qt::NoModifier);
  strip.mouseMoveEvent(&event);
  check(strip.mutationAttempts==(allowed?1:0),"actual mouse move lock/max gate");
  if(!allowed) {
   check(!strip.m_reordering,"locking mid-drag clears reorder state");
   check(strip.m_insertionGapIndex==-1,"locking mid-drag clears marker");
  }
  // Existing click selection remains available while locked/maximized.
  strip.setCurrentIndex(1);check(strip.currentIndex()==1,"tab selection remains usable");
 }
 DockingCheck::instance()->enabled=false;
 std::cout<<"PASS: actual merge/detach/reorder/event policy, locked/maximized/unlocked\n";
}
'''


def main():
    layout=(ROOT/'toonz/sources/toonzqt/docklayout.cpp').read_text()
    strip=(ROOT/'toonz/sources/toonzqt/docktabstrip.cpp').read_text()
    bodies='\n'.join(function(layout, signature) for signature in (
        'bool DockLayout::supportsTabGrouping(', 'bool DockLayout::canMergeAsTabs(',
        'void DockLayout::mergePanelsAsTabs(', 'void DockLayout::reorderTab(',
        'bool DockLayout::detachTabForDrag('))
    bodies+='\n'+function(strip,'void DockTabStrip::mouseMoveEvent(')
    flags=shlex.split(subprocess.check_output(
        ['pkg-config','--cflags','--libs','Qt5Widgets'],text=True))
    with tempfile.TemporaryDirectory(prefix='dock-tab-lock-') as directory:
        cpp, executable=Path(directory)/'test.cpp',Path(directory)/'test'
        cpp.write_text(FIXTURE+'\n'+bodies+'\n'+MAIN)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-fPIC',str(cpp),
                        '-o',str(executable),*flags],check=True)
        subprocess.run([str(executable)],env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),
                       check=True,timeout=30)


if __name__=='__main__':
    main()
