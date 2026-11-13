#!/usr/bin/env python3
"""Exercise actual geometry/dimension helpers under UBSan, without rendering."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
REFERENCE=ROOT if (ROOT/'toonz/sources/include/tgeometry.h').exists() else Path('/private/tmp/ivx-fork-sync-2026-11-12/clones-c/opentoonz')


def function(source,signature):
    start=source.index(signature);opening=source.index('{',start);depth,end=1,opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


MAIN=r'''
void check(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
template<class Function> void rejects(Function f){bool rejected=false;try{f();}catch(const TException &){rejected=true;}check(rejected,"unsupported geometry did not fail before conversion/allocation");}
int main(){
 const TRenderSettings identity{TAffine()};
 int rejected=0;
 for(double bad:{std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()}){
  rejects([&]{ShadowGeometry g(identity,bad,2,1,0,10);});
  rejects([&]{ShadowGeometry g(identity,4,bad,1,0,10);});
  rejects([&]{ShadowGeometry g(identity,4,2,1,bad,10);});
  rejects([&]{ShadowGeometry g(identity,4,2,1,0,bad);});rejected+=4;
 }
 rejects([&]{ShadowGeometry g(TRenderSettings{TScale(1e300)},4,2,1,0,10);});++rejected;
 rejects([&]{ShadowGeometry g(identity,1e300,2,15,0,10);});++rejected;
 rejects([&]{ShadowGeometry g(identity,4,1e300,15,0,10);});++rejected;
 rejects([&]{ShadowGeometry g(identity,4,2,1,0,1e300);});++rejected;
 rejects([&]{ShadowGeometry g(identity,4,2,1,0,-1e300);});++rejected;
 rejects([&]{ShadowGeometry g(identity,4,2,1,1e308,10);});++rejected;
 rejects([&]{ShadowGeometry g(TRenderSettings{TScale(2)},std::numeric_limits<double>::max(),2,1,0,10);});++rejected;
 const int limit=(std::numeric_limits<int>::max)();
 rejects([&]{blurReach(1e300,15);});++rejected;
 rejects([&]{roundedOffset(double(limit)+1);});++rejected;
 rejects([&]{roundedOffset(-double(limit)-1);});++rejected;
 rejects([&]{inputPadding(limit,1);});++rejected;
 rejects([&]{ShadowGeometry g(identity,0,0,0,0,double(limit));});++rejected;
 rejects([&]{checkedRasterSize(limit,1,1,0);});++rejected;
 rejects([&]{checkedRasterSize(1,limit,0,1);});++rejected;
 rejects([&]{checkedRasterSize(1,1,limit,0);});++rejected;
 rejects([&]{checkedRasterSize(limit,limit,0,0);});++rejected;
 rejects([&]{checkedRasterSize(0,1,0,0);});++rejected;
 rejects([&]{checkedRasterSize(1,1,-1,0);});++rejected;
 auto high=boxRange(limit-1,limit,limit-1);
 check(high.first==0 && high.second==limit,"near-INT_MAX support window overflowed");
 auto low=boxRange(0,limit,limit-1);
 check(low.first==0 && low.second==limit,"low support window overflowed");
 auto ordinary=boxRange(5,10,2);
 check(ordinary.first==3 && ordinary.second==8,"ordinary support window changed");
 std::vector<float> impulse={0,0,1,0,0},line;
 std::vector<double> prefix;
 boxPass(impulse.data(),5,1,3,prefix,line);
 check(impulse[0]==0 && impulse[4]==0 && std::abs(impulse[1]-1.f/3)<1e-7 && impulse[1]==impulse[2] && impulse[2]==impulse[3],"ordinary fractional box samples changed");
 for(double width:{4294967295.0,4294967297.0}){
  std::vector<float> tiny={1,1};
  boxPass(tiny.data(),2,1,width,prefix,line);
  check(tiny[0]==0 && tiny[1]==0,"wide kernel small-array sample changed");
 }
 for(double width:{1e300,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()}){
  rejects([&]{boxPass(impulse.data(),5,1,width,prefix,line);});++rejected;
 }
 ShadowGeometry normal(identity,4,2,2,0,10);
 check(normal.widthX==4 && normal.widthY==2 && normal.dx==10 && normal.dy==0,"supported geometry changed");
 check(normal.reachX==5 && normal.reachY==3 && normal.padX==15 && normal.padY==3,"supported blur/padding changed");
 ShadowGeometry zeroQuality(identity,1e300,1e300,0,0,0);
 check(zeroQuality.passes==0 && zeroQuality.reachX==1 && zeroQuality.padX==1,"zero-pass finite blur compatibility changed");
 ShadowGeometry fractional(TRenderSettings{TScale(2)},1.5,.5,1,0,1.25);
 check(fractional.widthX==3 && fractional.widthY==1 && fractional.dx==3 && fractional.padX==5,"fractional half-away-from-zero rounding changed");
 ShadowGeometry negativeBlur(identity,-2,-4,1,0,-1.5);
 check(negativeBlur.widthX==0 && negativeBlur.widthY==0 && negativeBlur.dx==-2,"finite negative blur/offset compatibility changed");
 TDimension size=checkedRasterSize(2,3,4,5);check(size.lx==10 && size.ly==13,"ordinary expanded dimensions changed");
 check(roundedOffset(double(limit))==limit && roundedOffset(-double(limit))==-limit,"representable offset boundary rejected");
 std::cout<<rejected<<" unsupported geometry/storage cases rejected under UBSan; normal/fractional/zero-pass compatibility PASS\n";
}
'''


def main():
    helpers=(ROOT/'toonz/sources/stdfx/shadowbevelutils.h').read_text()
    geometry=function(helpers,'struct ShadowGeometry')+';'
    bodies='\n'.join(function(helpers,sig) for sig in ['inline std::pair<int, int> boxRange(', 'inline void boxPass(', 'inline void requireFinite(', 'inline int roundedOffset(', 'inline int blurReach(', 'inline int inputPadding(', 'inline TDimension checkedRasterSize('])
    affine=(REFERENCE/'toonz/sources/common/tgeometry/tgeometry.cpp').read_text()
    cpp='''#include "tgeometry.h"
#include "texception.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>
#include <vector>
#include <iostream>
#include <stdexcept>
struct TRenderSettings { TAffine m_affine; };
'''+function(affine,'double TAffine::det() const')+'\n'+bodies+'\n'+geometry+'\n'+MAIN
    source=(ROOT/'toonz/sources/stdfx/dropshadowfx.cpp').read_text()
    compute=function(source,'void DropShadowFx::doCompute(')
    check='shadowbevel::checkedRasterSize(lx, ly, padX, padY)'
    assert compute.index(check)<compute.index('m_input->allocateAndCompute('), 'size guard must precede raster allocation'
    assert 'inputSize, out,' in compute, 'allocation must consume checked dimensions'
    with tempfile.TemporaryDirectory(prefix='ot-shadow-numeric-') as directory:
        path=Path(directory)/'test.cpp';binary=Path(directory)/'test';path.write_text(cpp)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-DMACOSX' if sys.platform=='darwin' else '-DLINUX','-fsanitize=undefined,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(REFERENCE/'toonz/sources/include'),str(path),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)


if __name__=='__main__':main()
