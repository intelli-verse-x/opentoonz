// Raster and blur helpers shared by Drop Shadow and Bevel FX.
// Box-blur sampling and pass rounding match Flash / Adobe Animate filters.
#pragma once

#include "stdfx.h"
#include "tpixelutils.h"
#include "texception.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>
#include <vector>

namespace shadowbevel {

// A premultiplied RGBA float copy of a raster region.
struct FloatImage {
  int lx = 0, ly = 0;
  std::vector<float> pixels;  // r, g, b, m per pixel
  float *at(int x, int y) { return &pixels[4 * (size_t(y) * lx + x)]; }
};

template <class PIXEL>
void readRaster(const TRasterPT<PIXEL> &ras, FloatImage &image) {
  image.lx = ras->getLx(), image.ly = ras->getLy();
  image.pixels.assign(4 * size_t(image.lx) * image.ly, 0.f);
  const float max = float(PIXEL::maxChannelValue);
  for (int y = 0; y < image.ly; ++y) {
    const PIXEL *pix = ras->pixels(y);
    for (int x = 0; x < image.lx; ++x, ++pix) {
      float *out = image.at(x, y);
      out[0] = pix->r / max, out[1] = pix->g / max, out[2] = pix->b / max;
      out[3] = pix->m / max;
    }
  }
}

template <>
inline void readRaster<TPixelF>(const TRasterFP &ras, FloatImage &image) {
  image.lx = ras->getLx(), image.ly = ras->getLy();
  image.pixels.assign(4 * size_t(image.lx) * image.ly, 0.f);
  for (int y = 0; y < image.ly; ++y) {
    const TPixelF *pix = ras->pixels(y);
    for (int x = 0; x < image.lx; ++x, ++pix) {
      float *out = image.at(x, y);
      out[0] = pix->r, out[1] = pix->g, out[2] = pix->b, out[3] = pix->m;
    }
  }
}

template <class PIXEL>
void writePixel(PIXEL &pix, const float *value) {
  const float max = float(PIXEL::maxChannelValue);
  auto channel    = [max](float v) {
    return (typename PIXEL::Channel)std::lround(
           std::max(0.f, std::min(1.f, v)) * max);
  };
  pix.r = channel(value[0]), pix.g = channel(value[1]);
  pix.b = channel(value[2]), pix.m = channel(value[3]);
}

template <>
inline void writePixel<TPixelF>(TPixelF &pix, const float *value) {
  pix.r = value[0], pix.g = value[1], pix.b = value[2];
  pix.m = std::max(0.f, std::min(1.f, value[3]));
}

// Keep support-window index arithmetic wider than the raster's int indices.
inline std::pair<int, int> boxRange(int index, int count, int radius) {
  const long long center = index;
  return {static_cast<int>(std::max(0LL, center - radius)),
          static_cast<int>(
              std::min(static_cast<long long>(count), center + radius + 1))};
}

// One 1D box pass of width `width` pixels on `values` (stride `step`), as the
// Flash Player blurs: taps -(m+1)..(m+1) around each pixel, the two outer
// ones weighted by the fractional part, divided by the width and rounded
// down to 8 bits. Samples outside are zero.
inline void boxPass(float *values, int count, int step, double width,
                    std::vector<double> &prefix, std::vector<float> &line) {
  if (!std::isfinite(width))
    throw TException(L"Drop Shadow: non-finite blur kernel");
  if (width <= 1 || count <= 0) return;
  const double radius = (width - 1) / 2;
  const double taps   = std::ceil(radius) - 1;
  if (taps > (std::numeric_limits<int>::max)())
    throw TException(L"Drop Shadow: blur kernel exceeds integer geometry");
  const int m       = static_cast<int>(taps);
  const double edge = std::floor((radius - m) * 255) / 255;
  prefix.assign(size_t(count) + 1, 0.0);
  line.resize(count);
  for (int i = 0; i < count; ++i) {
    line[i]       = values[size_t(i) * step];
    prefix[i + 1] = prefix[i] + line[i];
  }
  auto sample = [&](long long i) {
    return i < 0 || i >= count ? 0.f : line[static_cast<size_t>(i)];
  };
  for (int i = 0; i < count; ++i) {
    const auto range = boxRange(i, count, m);
    const int low = range.first, high = range.second;
    const long long center = i;
    double total           = high > low ? prefix[high] - prefix[low] : 0.0;
    total += edge * (sample(center - m - 1) + sample(center + m + 1));
    const double v           = std::floor(total / width * 255 + 1e-6) / 255;
    values[size_t(i) * step] = float(std::max(0.0, std::min(1.0, v)));
  }
}

// Blurs the alpha plane `alpha` (lx * ly) in place.
inline void boxBlur(std::vector<float> &alpha, int lx, int ly, double widthX,
                    double widthY, int passes) {
  std::vector<double> prefix;
  std::vector<float> line;
  for (int pass = 0; pass < passes; ++pass) {
    if (widthX > 1)
      for (int y = 0; y < ly; ++y)
        boxPass(&alpha[size_t(y) * lx], lx, 1, widthX, prefix, line);
    if (widthY > 1)
      for (int x = 0; x < lx; ++x)
        boxPass(&alpha[x], ly, lx, widthY, prefix, line);
  }
}

// Reject geometry that cannot be represented before integer conversions or
// raster dimension arithmetic. Ordinary finite geometry keeps its rounding.
inline void requireFinite(double value) {
  if (!std::isfinite(value))
    throw TException(L"Drop Shadow: non-finite geometry");
}

inline int roundedOffset(double value) {
  requireFinite(value);
  const double rounded = std::round(value);
  const double limit   = (std::numeric_limits<int>::max)();
  if (rounded < -limit || rounded > limit)
    throw TException(L"Drop Shadow: offset exceeds integer geometry");
  return static_cast<int>(rounded);
}

// Pixels a blur of this width and passes reaches on each side. Reserve one
// integer pixel for the existing outer sampling margin.
inline int blurReach(double width, int passes) {
  requireFinite(width);
  if (width <= 1 || passes <= 0) return 0;
  const double radius = std::ceil((width - 1) / 2);
  const int limit     = (std::numeric_limits<int>::max)() - 1;
  if (radius > limit / passes)
    throw TException(L"Drop Shadow: blur exceeds integer geometry");
  return passes * static_cast<int>(radius);
}

inline int inputPadding(int reach, int offset) {
  const long long padding =
      static_cast<long long>(reach) + std::abs(static_cast<long long>(offset));
  if (padding > (std::numeric_limits<int>::max)())
    throw TException(L"Drop Shadow: input padding exceeds integer geometry");
  return static_cast<int>(padding);
}

inline TDimension checkedRasterSize(int lx, int ly, int padX, int padY) {
  const long long width  = static_cast<long long>(lx) + 2LL * padX;
  const long long height = static_cast<long long>(ly) + 2LL * padY;
  const int limit        = (std::numeric_limits<int>::max)();
  if (lx <= 0 || ly <= 0 || padX < 0 || padY < 0 || width > limit ||
      height > limit)
    throw TException(L"Drop Shadow: expanded raster exceeds integer geometry");
  const size_t maxPixels = std::vector<float>().max_size() / 4;
  if (static_cast<unsigned long long>(width) >
      maxPixels / static_cast<unsigned long long>(height))
    throw TException(
        L"Drop Shadow: expanded raster storage is unrepresentable");
  return TDimension(static_cast<int>(width), static_cast<int>(height));
}

inline void premultipliedColor(const TPixelD &color, float *out) {
  out[0] = float(color.r * color.m), out[1] = float(color.g * color.m);
  out[2] = float(color.b * color.m), out[3] = float(color.m);
}

// Shared geometry of the shadow FX: the blur in output pixels and the
// offset of the shadow (raster Y points up).
struct ShadowGeometry {
  double widthX = 0, widthY = 0;
  int passes = 1;
  int dx = 0, dy = 0;  // rounded to whole pixels, as Flash samples them
  int reachX = 0, reachY = 0;
  int padX = 0, padY = 0;

  ShadowGeometry(const TRenderSettings &info, double blurX, double blurY,
                 int quality, double angle, double distance) {
    requireFinite(blurX);
    requireFinite(blurY);
    requireFinite(angle);
    requireFinite(distance);
    const double scale = std::sqrt(std::abs(info.m_affine.det()));
    requireFinite(scale);
    requireFinite(blurX * scale);
    requireFinite(blurY * scale);
    widthX               = std::max(0.0, blurX * scale);
    widthY               = std::max(0.0, blurY * scale);
    passes               = std::max(0, std::min(15, quality));
    const double radians = angle * std::acos(-1.0) / 180;
    requireFinite(radians);
    dx     = roundedOffset(distance * scale * std::cos(radians));
    dy     = roundedOffset(-distance * scale * std::sin(radians));
    reachX = blurReach(widthX, passes) + 1;
    reachY = blurReach(widthY, passes) + 1;
    padX   = inputPadding(reachX, dx);
    padY   = inputPadding(reachY, dy);
  }
};

}  // namespace shadowbevel
