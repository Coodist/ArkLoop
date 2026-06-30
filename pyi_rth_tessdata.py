import os, sys

base = os.path.dirname(sys.executable)
tess_dir = os.path.join(base, '_internal', 'Tesseract-OCR')
os.environ['TESSDATA_PREFIX'] = os.path.join(tess_dir, 'tessdata')
os.environ['PATH'] = tess_dir + os.pathsep + os.environ.get('PATH', '')
