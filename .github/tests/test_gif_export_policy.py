"""Compile the actual pure GIF filter branch; no GUI, media file, or ffmpeg runs."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class GifExportPolicy(unittest.TestCase):
    def test_default_preserves_frame_rate_colors_and_opt_in_filters(self):
        source = (ROOT / 'toonz/sources/image/ffmpeg/tiio_gif.cpp').read_text()
        header = (ROOT / 'toonz/sources/image/ffmpeg/tiio_gif.h').read_text()
        property_default = re.search(r'm_optimize\("Optimize",\s*(true|false)\)', source).group(1)
        writer_default = re.search(r'bool\s+m_optimize\s*=\s*(true|false);', header).group(1)
        # Use the real reviewed C++ filter body, avoiding an independent
        # reimplementation that could pass while the writer regressed.
        start = source.index('  QString filters;')
        end = source.index('  // Set up FFmpeg arguments', start)
        body = source[start:end]
        program = r'''
#include <QString>
#include <cassert>
QString actualFilter(bool m_optimize, double framerate, int m_mode,
                     int m_maxcolors, int outLx, int outLy) {
BODY
  return filters;
}
int main() {
  const bool propertyDefault = PROPERTY_DEFAULT;
  const bool writerDefault = WRITER_DEFAULT;
  assert(!propertyDefault && !writerDefault);
  for (int mode = 0; mode <= 12; ++mode) {
    auto normal = actualFilter(propertyDefault, 24.0, mode, 16, 320, 240);
    assert(normal.startsWith("[0:v]fps=24,scale=320:240:flags=lanczos"));
    assert(!normal.contains("fps=5") && !normal.contains("max_colors=32"));
    if (mode < 12) assert(normal.contains("max_colors=16"));
    if (mode >= 8 && mode < 12) assert(normal.contains("paletteuse=new=1"));
    if (mode == 0) assert(normal.contains("dither=none"));
    if (mode == 2) assert(normal.contains("bayer_scale=2"));
    if (mode == 3) assert(normal.contains("bayer_scale=1"));
  }
  auto optimized = actualFilter(true, 24.0, 1, 256, 320, 240);
  assert(optimized.startsWith("[0:v]fps=5:round=up,scale=320:240"));
  assert(optimized.contains("palettegen=max_colors=32:stats_mode=diff"));
  assert(optimized.contains("reserve_transparent=1") && optimized.contains("diff_mode=rectangle"));
  assert(actualFilter(true, 1.0, 1, 256, 320, 240).contains("fps=1:round=up"));
}
'''.replace('BODY', body).replace('PROPERTY_DEFAULT', property_default).replace('WRITER_DEFAULT', writer_default)
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt5Core'], env=env, text=True))
        with tempfile.TemporaryDirectory(prefix='owned-gif-policy-') as temporary:
            cpp = Path(temporary) / 'policy.cpp'
            binary = Path(temporary) / 'policy'
            cpp.write_text(program)
            subprocess.run(['c++', '-std=c++11', '-fPIC', str(cpp), '-o', str(binary), *flags], env=env, check=True, timeout=60)
            subprocess.run([str(binary)], env=env, check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
