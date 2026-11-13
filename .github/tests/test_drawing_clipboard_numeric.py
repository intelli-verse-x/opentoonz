#!/usr/bin/env python3
"""Run the actual decoder body with real Qt serialization and image classes.

Domain raster/palette adapters are inert boundary counters, not renderer tests.
The malformed metadata must be rejected before either adapter is called.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2] if '.github' in str(Path(__file__).resolve()) else Path(__file__).resolve().parent
SOURCE = ROOT / 'toonz/sources/tnztools/rasterselection.cpp'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


FIXTURE = r'''
#include <QDataStream>
#include <QMimeData>
#include <QImage>
#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <vector>
const char *const DrawingClipboardFormat = "application/x-opentoonz-raster-selection-v1";
int paletteCalls=0, rasterCalls=0, resultCalls=0;
struct TPalette {};
using TPaletteP=std::shared_ptr<TPalette>;
TPaletteP paletteFromBytes(const QByteArray &) { ++paletteCalls; return std::make_shared<TPalette>(); }
using TPixelCM32=quint32;
struct Raster {
 int w,h; std::vector<quint32> data;
 Raster(int w,int h):w(w),h(h),data(w*h){}
 quint32 *pixels(int y){return data.data()+y*w;}
 std::pair<int,int> getSize() const{return {w,h};}
};
using TRasterP=std::shared_ptr<Raster>;
struct TRasterCM32P: TRasterP { TRasterCM32P(int w,int h):TRasterP(std::make_shared<Raster>(w,h)){} };
TRasterP rasterFromQImage(const QImage &image){++rasterCalls;return std::make_shared<Raster>(image.width(),image.height());}
struct TRectD {
 double x0,y0,x1,y1;
 TRectD(double a,double b,double c,double d):x0(a),y0(b),x1(c),y1(d){}
 bool isEmpty()const{return x0>x1 || y0>y1;}
};
struct TStroke {};
TStroke getStrokeByRect(TRectD){return {};}
struct TAffine {TAffine(double,double,double,double,double,double){}};
struct RasterImageData {
 virtual ~RasterImageData()=default;
 void setData(TRasterP,TPaletteP,double,double,std::pair<int,int>,std::vector<TRectD>,std::vector<TStroke>,std::vector<TStroke>,TAffine){++resultCalls;}
};
struct ToonzImageData:RasterImageData {};
struct FullColorImageData:RasterImageData {};
void check(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
'''

MAIN = r'''
QByteArray payload(const std::array<double,12> &v,bool cm=false,quint32 version=1){
 QByteArray bytes;QDataStream out(&bytes,QIODevice::WriteOnly);out.setVersion(QDataStream::Qt_5_15);
 out<<version<<cm;
 for(double value:v)out<<value;
 out<<QByteArray();
 if(cm){QByteArray pixels;QDataStream values(&pixels,QIODevice::WriteOnly);values<<quint32(0);out<<1<<1<<qCompress(pixels);}
 else{QImage image(1,1,QImage::Format_ARGB32);image.fill(Qt::transparent);out<<image;}
 return bytes;
}
int main(){
 const std::array<double,12> valid={72,72,0,0,1,1,1,0,0,0,1,0};
 int rejected=0;
 for(bool cm:{false,true})for(int field=0;field<12;++field)
  for(double bad:{std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()}){
   auto values=valid;values[field]=bad;QMimeData mime;mime.setData(DrawingClipboardFormat,payload(values,cm));
   int p=paletteCalls,r=rasterCalls,s=resultCalls;
   check(!decodeDrawing(&mime),"nonfinite metadata accepted");
   check(paletteCalls==p && rasterCalls==r && resultCalls==s,"nonfinite metadata reached domain adapters");++rejected;
  }
 for(bool cm:{false,true}){
  QMimeData mime;mime.setData(DrawingClipboardFormat,payload(valid,cm));check(bool(decodeDrawing(&mime)),"valid serialized drawing rejected");
  auto zero=valid;zero[0]=zero[1]=0;mime.setData(DrawingClipboardFormat,payload(zero,cm));check(bool(decodeDrawing(&mime)),"unknown zero DPI rejected");
  auto affine=valid;affine[6]=-2;affine[7]=.3;affine[8]=-100;affine[9]=.7;affine[10]=3;affine[11]=20;
  mime.setData(DrawingClipboardFormat,payload(affine,cm));check(bool(decodeDrawing(&mime)),"legitimate finite affine rejected");
 }
 QMimeData wrong;wrong.setData(DrawingClipboardFormat,payload(valid,false,2));check(!decodeDrawing(&wrong),"wrong version accepted");
 QMimeData truncated;truncated.setData(DrawingClipboardFormat,payload(valid).left(20));check(!decodeDrawing(&truncated),"truncated header accepted");
 std::cout<<rejected<<" nonfinite metadata cases rejected before adapters; 6 finite compatibility cases PASS\n";
}
'''


def main():
    decoder = function(SOURCE.read_text(), 'std::unique_ptr<RasterImageData> decodeDrawing(')
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt5Gui', 'Qt5Core'], text=True))
    with tempfile.TemporaryDirectory(prefix='ot-clipboard-numeric-') as directory:
        cpp=Path(directory)/'test.cpp'; binary=Path(directory)/'test'
        cpp.write_text(FIXTURE+'\n'+decoder+'\n'+MAIN)
        subprocess.run([os.environ.get('CXX','c++'), '-std=c++17', '-fPIC', str(cpp), '-o', str(binary), *flags], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
