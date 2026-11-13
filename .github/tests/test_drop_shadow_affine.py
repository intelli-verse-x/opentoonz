#!/usr/bin/env python3
"""Compile actual FX policy, renderer affine predicate and shadow geometry.

Uses the project's real affine header/operations; this verifies geometry and
fallback routing, not pixel-equivalence or interactive rendering.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2] if '.github' in str(Path(__file__).resolve()) else Path(__file__).resolve().parent
# A staged review can use the reference checkout for unchanged dependencies.
REFERENCE = ROOT if (ROOT/'toonz/sources/include/tgeometry.h').exists() else Path('/private/tmp/ivx-fork-sync-2026-11-12/clones-c/opentoonz')


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


MAIN = r'''
void check(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
void close(double a,double b,const char *message){check(std::abs(a-b)<1e-9,message);}
int main(){
 DropShadowFx fx;
 const std::vector<TAffine> affines={TAffine(),TScale(2),TAffine(2,0,0,0,.5,0),TAffine(0,-1,0,1,0,0),TScale(-1),TScale(-1,1),TAffine(1,.5,0,0,1,0),TAffine(1,0,13,0,1,-8)};
 for(size_t i=0;i<affines.size();++i){
  TRenderSettings settings{affines[i]};
  const bool direct=frameworkCanHandle(fx,settings,0);
  check(direct==(i<2),"nonlocal affine must use renderer fallback; positive uniform stays direct");
  const TAffine handled=fx.handledAffine(settings,0);
  const TAffine base=fx.TRasterFx::handledAffine(settings,0);
  check(handled.a11>0 && handled.a22==handled.a11,"handled scale must be positive uniform");
  close(handled.a11,std::abs(base.a11),"preserve base sampling resolution");
  TRenderSettings local{handled};
  ShadowGeometry geometry(local,4,2,1,0,10);
  TAffine remainder=settings.m_affine*handled.inv();
  TPointD displacement=remainder.transformDirection(TPointD(geometry.dx,geometry.dy));
  TPointD expected=settings.m_affine.transformDirection(TPointD(10,0));
  check(std::abs(displacement.x-expected.x)<=.5*(std::abs(remainder.a11)+std::abs(remainder.a12))+1e-9,"shadow x displacement follows full affine within integer sampling");
  check(std::abs(displacement.y-expected.y)<=.5*(std::abs(remainder.a21)+std::abs(remainder.a22))+1e-9,"shadow y displacement follows full affine within integer sampling");
  close(geometry.widthX,4*handled.a11,"blur x uses handled sampling");
  close(geometry.widthY,2*handled.a11,"blur y uses handled sampling");
 }
 // Explicitly demonstrate the old determinant-only 180-degree displacement.
 ShadowGeometry oldGeometry(TRenderSettings{TScale(-1)},0,0,0,0,10);
 check(oldGeometry.dx==10,"fixture must reproduce old half-turn sign mismatch");
 std::cout<<"8 affine routing/displacement/blur cases PASS; includes 180-degree fallback\n";
}
'''


def main():
    renderer=(REFERENCE/'toonz/sources/tnzbase/trasterfx.cpp').read_text()
    fx_source=(ROOT/'toonz/sources/stdfx/dropshadowfx.cpp').read_text()
    helpers=(ROOT/'toonz/sources/stdfx/shadowbevelutils.h').read_text()
    geometry=function(helpers,'struct ShadowGeometry')+';'
    predicate=re.search(r'bool canHandleAffine\s*=\s*(canHandle\(info, frame\).*?);',renderer,re.S).group(1)
    policy=function(fx_source,'bool canHandle(').replace(' override','')
    handled=function(fx_source,'TAffine handledAffine(').replace(' override','')
    base=function(renderer,'TAffine TRasterFx::handledAffine(')
    norm=function(renderer,'double norm2(const TAffine &aff)')
    # Actual affine implementations needed by the isolated geometry fixture.
    affine_source=(REFERENCE/'toonz/sources/common/tgeometry/tgeometry.cpp').read_text()
    operations='\n'.join(function(affine_source,sig) for sig in ['TAffine TAffine::operator*(const TAffine &b) const','TAffine TAffine::inv() const','double TAffine::det() const','bool TAffine::operator==(const TAffine &a) const','TPointD TAffine::transformDirection(const TPointD &p) const'])
    code='''#include "tgeometry.h"
#include "texception.h"
#include <limits>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>
struct TRenderSettings { TAffine m_affine; };
class TRasterFx { public: virtual TAffine handledAffine(const TRenderSettings &,double); };
'''+operations+'\n'+norm+'\n'+base+'\n'+'\n'.join(function(helpers, signature) for signature in ['inline void requireFinite(', 'inline int roundedOffset(', 'inline int blurReach(', 'inline int inputPadding('])+'\n'+geometry+'''
class DropShadowFx:public TRasterFx { public:
'''+policy+'\n'+handled+'''
 bool route(const TRenderSettings &info,double frame){return '''+predicate+''';}
};
bool frameworkCanHandle(DropShadowFx &fx,const TRenderSettings &info,double frame){return fx.route(info,frame);}
'''+MAIN
    with tempfile.TemporaryDirectory(prefix='ot-shadow-affine-') as directory:
        cpp=Path(directory)/'test.cpp';binary=Path(directory)/'test';cpp.write_text(code)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17', '-DMACOSX' if sys.platform=='darwin' else '-DLINUX','-I'+str(REFERENCE/'toonz/sources/include'),str(cpp),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)


if __name__=='__main__':main()
