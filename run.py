import os
import sys

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

tessdata_path = os.path.join(application_path, "_internal", "Tesseract-OCR", "tessdata")
os.environ['TESSDATA_PREFIX'] = tessdata_path

from src.main import main
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PRTS+')
    parser.add_argument('--axis', type=str, help='The path to the JSON axis file.')
    parser.add_argument('--xlsm', type=str, help='The path to the Excel file.')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode.')
    parser.add_argument('--autoenter', action='store_true', help='Run in auto enter mode.')
    parser.add_argument('--calibrate', action='store_true', help='Run cost bar calibration and save the result.')
    args = parser.parse_args()

    if not args.axis and not args.xlsm and not args.calibrate:
        parser.error("Either --axis, --xlsm or --calibrate must be provided.")

    main(args.axis, args.xlsm, args.debug, args.autoenter, args.calibrate)
