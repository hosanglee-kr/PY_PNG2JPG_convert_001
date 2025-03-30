"""
이 스크립트는 특정 폴더를 주기적으로 감시하여 새로 생성되거나 수정된 PNG 이미지 파일을 JPG 형식으로 변환하는 프로그램입니다.
Samba 공유 폴더 환경을 고려하여 watchdog 대신 폴더 스캔 방식을 사용하며, 멀티프로세싱을 제거하여 단일 프로세스로 동작합니다.
JPG 저장 폴더 구조는 원본 PNG 파일과 동일한 구조를 유지하며, 프로세스 재실행 시에도 문제없이 동작합니다.
변환된 JPG 파일은 다른 프로그램에서 5분에 한번씩 다른 폴더로 이동될 수 있는 환경을 고려하여 처리 로직을 개선했습니다.
처리된 PNG 파일 목록은 날짜별로 파일에 저장됩니다.

**주요 기능:**

1.  **주기적인 폴더 스캔:** 설정된 폴더를 지정된 시간 간격으로 검색하여 PNG 파일을 찾습니다.
2.  **PNG → JPG 변환:** 발견된 PNG 파일을 Pillow 라이브러리를 사용하여 JPG 형식으로 변환합니다.
3.  **원본 폴더 구조 유지:** 변환된 JPG 파일은 원본 PNG 파일과 동일한 폴더 구조를 `output_base_folder` 아래에 생성하여 저장합니다.
4.  **흑백/컬러 모드 유지:** 원본 PNG 파일의 흑백 또는 컬러 모드를 유지하여 JPG로 변환합니다.
5.  **처리된 파일 기록:** 처리된 PNG 파일의 경로는 날짜별 파일에 저장하여 스크립트 재실행 시 중복 처리를 방지합니다.
6.  **파일 안정성 확인:** 변환 전에 PNG 파일이 완전히 쓰여졌는지 확인하여 불완전한 파일 변환을 방지합니다.
7.  **로그 기록:** 발생하는 에러는 일자별 로그 파일에 기록하여 문제 발생 시 추적을 용이하게 합니다.
8.  **명령행 인자 처리:** 특정 날짜의 폴더만 처리할 수 있는 명령행 인자를 제공합니다.
9.  **설정 파일 사용:** 감시 폴더, 출력 폴더, 로그 폴더, JPG 품질 등의 설정을 외부 설정 파일(`config.ini`)에서 관리합니다.
10. **외부 파일 이동 고려:** 변환된 JPG 파일이 외부 프로그램에 의해 이동될 수 있는 상황을 고려하여 처리 로직을 개선했습니다.
"""
import os
import time
from PIL import Image
import re
import sys
from datetime import datetime
import logging
import argparse
import configparser  # configparser 라이브러리 추가

GLOBAL_GRAYSCALE_MODE = None  # 전역 변수로 이미지 모드 저장 (True: 흑백, False: 컬러, None: 미결정)
SCAN_INTERVAL = 60  # 폴더 스캔 간격 (초)
PROCESSED_FILES_PREFIX = "processed_files_" # 처리된 파일 목록 파일명 접두사

def get_processed_files_filename(log_folder, date_str=None):
    """날짜별 처리된 파일 목록 파일 이름을 생성합니다."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    return os.path.join(log_folder, f"{PROCESSED_FILES_PREFIX}{date_str}.txt")

def load_processed_files(log_folder):
    """오늘 날짜의 처리된 파일 목록을 파일에서 로드합니다."""
    today_str = datetime.now().strftime("%Y%m%d")
    filepath = get_processed_files_filename(log_folder, today_str)
    processed = set()
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            for line in f:
                processed.add(line.strip())
    return processed

def save_processed_files(log_folder, processed_set):
    """오늘 날짜의 처리된 파일 목록을 파일에 저장합니다."""
    today_str = datetime.now().strftime("%Y%m%d")
    filepath = get_processed_files_filename(log_folder, today_str)
    with open(filepath, 'w') as f:
        for item in processed_set:
            f.write(f"{item}\n")

def convert_image(input_path, output_base_folder, watch_base_folder, quality, processed_files):
    """
    단일 프로세스에서 이미지를 변환하는 함수입니다.
    원본 PNG의 흑백/컬러 모드를 유지하여 JPG로 변환합니다.
    JPG 저장 폴더 구조는 원본 PNG 파일과 동일한 구조를 유지합니다.

    Args:
        input_path (str): 변환할 PNG 파일의 전체 경로.
        output_base_folder (str): 변환된 JPG 파일을 저장할 최상위 폴더 경로.
        watch_base_folder (str): 감시 대상 최상위 폴더 경로 (상대 경로 계산에 사용).
        quality (int): JPG 이미지 품질 (0-100).
        processed_files (set): 이미 처리된 파일 경로를 저장하는 set.
    """
    global GLOBAL_GRAYSCALE_MODE
    try:
        print(f"Attempting to convert {input_path}")
        img = Image.open(input_path) # PNG 이미지 파일을 엽니다.

        # 원본 PNG 파일 경로를 기준으로 상대 경로를 생성합니다.
        relative_path = os.path.relpath(input_path, watch_base_folder)
        output_path = os.path.join(output_base_folder, relative_path)
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True) # 필요한 출력 폴더 구조를 생성합니다.

        filename, _ = os.path.splitext(os.path.basename(input_path)) # 입력 파일 이름에서 확장자를 제거합니다.
        temp_output_path = os.path.join(output_dir, f".temp_{filename}.jpg") # 임시 JPG 파일 경로를 생성합니다.
        final_output_path = os.path.join(output_dir, f"{filename}.jpg") # 최종 JPG 파일 경로를 생성합니다.

        if GLOBAL_GRAYSCALE_MODE is True:
            img = img.convert('L')  # 흑백으로 강제 변환
            img.save(temp_output_path, "JPEG", quality=quality) # JPG 파일로 저장합니다.
        elif GLOBAL_GRAYSCALE_MODE is False:
            img = img.convert('RGB') # 컬러로 강제 변환
            img.save(temp_output_path, "JPEG", quality=quality) # JPG 파일로 저장합니다.
        else:
            # 초기 판단에 실패했을 경우를 대비한 안전 장치 (기존 로직)
            if img.mode == 'L':
                img.save(temp_output_path, "JPEG", quality=quality) # 흑백 이미지인 경우 그대로 저장합니다.
            elif img.mode in ('RGBA', 'P'):
                img = img.convert('RGB') # 컬러 이미지 (알파 채널 포함 또는 팔레트 이미지)는 RGB로 변환합니다.
                img.save(temp_output_path, "JPEG", quality=quality) # JPG 파일로 저장합니다.
            elif img.mode == 'RGB':
                img.save(temp_output_path, "JPEG", quality=quality) # 이미 RGB인 경우 그대로 저장합니다.
            else:
                logging.warning(f"Unknown image mode '{img.mode}' for {input_path}. Converting to RGB.")
                img = img.convert('RGB') # 알 수 없는 모드의 경우 RGB로 변환합니다.
                img.save(temp_output_path, "JPEG", quality=quality) # JPG 파일로 저장합니다.

        os.rename(temp_output_path, final_output_path) # 임시 파일 이름을 최종 파일 이름으로 변경합니다.
        print(f"Converted {input_path} to {final_output_path} (Quality: {quality}, Mode: {'L' if GLOBAL_GRAYSCALE_MODE else 'RGB'})")
        processed_files.add(input_path) # 처리 완료 후 processed_files에 추가
    except FileNotFoundError:
        logging.error(f"Error - Input file not found: {input_path}")
    except PermissionError:
        logging.error(f"Error - Permission denied accessing file: {input_path} or {output_base_folder}")
    except Image.UnidentifiedImageError:
        logging.error(f"Error - Could not open or read image file: {input_path}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during conversion of {input_path}: {e}")

def is_stable(file_path, wait_time=1):
    """
    파일이 안정적인 상태인지 확인합니다.

    Args:
        file_path (str): 확인할 파일 경로.
        wait_time (int): 대기 시간 (초).

    Returns:
        bool: 파일이 안정적이면 True, 아니면 False.
    """
    try:
        initial_size = os.path.getsize(file_path) # 파일의 초기 크기를 얻습니다.
        time.sleep(wait_time) # 잠시 대기합니다.
        current_size = os.path.getsize(file_path) # 파일의 현재 크기를 얻습니다.
        return initial_size == current_size and current_size > 0
    except FileNotFoundError:
        logging.error(f"Error: File not found while checking stability: {file_path}")
        return False
    except PermissionError:
        logging.error(f"Error: Permission denied accessing file for stability check: {file_path}")
        return False
    except Exception as e:
        logging.error(f"Error during file stability check for {file_path}: {e}")
        return False

if __name__ == "__main__":
    # 설정 파일 읽기
    config = configparser.ConfigParser()
    config.read('config.ini')

    # 설정 파일에서 감시 폴더, 출력 폴더, 로그 폴더, JPG 품질 설정을 읽어옵니다.
    watch_base_folder = config['Paths']['watch_base_folder']
    output_base_folder = config['Paths']['output_base_folder']
    log_folder = config['Paths']['log_folder']
    jpg_quality = int(config['Image']['jpg_quality'])

    # 로그 폴더가 존재하지 않으면 생성합니다.
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    # 로그 파일 이름을 현재 날짜를 기반으로 설정합니다 (error_YYYYMMDD.log 형식).
    today = datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(log_folder, f"error_{today}.log")

    # 로깅 설정을 구성합니다. 에러 메시지를 로그 파일에 기록하고, 메시지 형식과 로그 레벨을 설정합니다.
    logging.basicConfig(
        filename=log_filename,
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 명령행 인수를 처리하기 위한 ArgumentParser를 생성합니다.
    parser = argparse.ArgumentParser(description="Convert PNG images to JPG.")
    # 특정 날짜의 폴더만 처리하기 위한 명령행 인수를 추가합니다.
    parser.add_argument("date", nargs="?", help="Process folder for a specific date (YYYYMMDD). If not provided, processes today's date.")
    args = parser.parse_args() # 명령행 인수를 파싱합니다.

    # 명령행 인자로 날짜가 제공되었는지 확인하고, 처리할 대상 폴더를 결정합니다.
    if args.date:
        target_date_str = args.date
        # 입력된 날짜 형식이endedorMMDD인지 정규표현식으로 확인합니다.
        if re.match(r'^\d{8}$', target_date_str):
            watch_folder = os.path.join(watch_base_folder, target_date_str)
            print(f"Processing folder for date: {target_date_str} ({watch_folder})")
        else:
            print("Invalid date format. Please use 명령어: python your_script_name.py<\ctrl98>MMDD")
            sys.exit(1)
    else:
        # 명령행 인자로 날짜가 제공되지 않은 경우, 현재 날짜를 기준으로 처리할 폴더를 설정합니다.
        now = datetime.now()
        target_date_str = now.strftime("%Y%m%d")
        watch_folder = os.path.join(watch_base_folder, target_date_str)
        print(f"Processing folder for today's date: {target_date_str} ({watch_folder})")

    # 스크립트 시작 시 오늘 날짜의 처리된 파일 목록을 로드합니다.
    processed_files = load_processed_files(log_folder)

    # 무한 루프를 시작하여 폴더를 주기적으로 스캔하고 PNG 파일을 처리합니다.
    while True:
        # 감시 대상 폴더가 실제로 존재하는지 확인합니다.
        if os.path.exists(watch_folder):
            # 스크립트 시작 시 또는 주기적인 스캔 시 global grayscale mode를 결정합니다.
            GLOBAL_GRAYSCALE_MODE = None
            # 감시 폴더 및 하위 폴더를 순회하며 PNG 파일을 찾습니다.
            for root, _, files in os.walk(watch_folder):
                for filename in files:
                    if filename.lower().endswith(".png"):
                        first_png_path = os.path.join(root, filename)
                        try:
                            with Image.open(first_png_path) as img:
                                if img.mode == 'L':
                                    GLOBAL_GRAYSCALE_MODE = True
                                    print("Detected grayscale mode for all images.")
                                else:
                                    GLOBAL_GRAYSCALE_MODE = False
                                    print("Detected color mode for all images.")
                                break  # 첫 번째 PNG 파일만 확인
                        except Exception as e:
                            logging.error(f"Error opening first PNG file for mode detection: {first_png_path} - {e}")
                        if GLOBAL_GRAYSCALE_MODE is not None:
                            break
                if GLOBAL_GRAYSCALE_MODE is not None:
                    break
            if GLOBAL_GRAYSCALE_MODE is None:
                print("No PNG files found to determine global color mode. Defaulting to color conversion.")
                GLOBAL_GRAYSCALE_MODE = False # 기본적으로 컬러로 설정

            print(f"Scanning folder: {watch_folder}")
            # 감시 폴더 및 하위 폴더를 순회하며 PNG 파일을 찾습니다.
            for root, _, files in os.walk(watch_folder):
                for filename in files:
                    if filename.lower().endswith(".png"):
                        png_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(png_path, watch_base_folder)
                        output_path = os.path.join(output_base_folder, relative_path.replace(".png", ".jpg"))

                        # 아직 처리되지 않았고, JPG 파일이 존재하지 않는 경우
                        if png_path not in processed_files and not os.path.exists(output_path):
                            print(f"Found potentially new PNG: {png_path}")
                            # 파일이 안정적인 상태인지 확인 후 변환을 시도합니다.
                            if is_stable(png_path):
                                convert_image(png_path, output_base_folder, watch_base_folder, jpg_quality, processed_files)
                            else:
                                print(f"PNG file not yet stable: {png_path}")
                        # 이미 처리된 파일 목록에 있지만, JPG 파일이 없는 경우 (이전 실행 실패 또는 JPG 파일이 이동되었을 수 있음) 다시 변환을 시도합니다.
                        elif png_path in processed_files and not os.path.exists(output_path):
                            print(f"Re-converting (JPG missing): {png_path}")
                            if is_stable(png_path):
                                convert_image(png_path, output_base_folder, watch_base_folder, jpg_quality, processed_files)
                            else:
                                print(f"PNG file not yet stable: {png_path}")
                        # JPG 파일이 이미 존재하고, processed_files에 없는 경우 (이전 실행에서 처리됨) processed_files에 추가합니다.
                        elif os.path.exists(output_path) and png_path not in processed_files:
                            processed_files.add(png_path)
                            print(f"PNG already processed (JPG exists): {png_path}")

        else:
            print(f"Error: Watch folder does not exist: {watch_folder}")

        # 현재 처리된 파일 목록을 오늘 날짜의 파일에 저장합니다.
        save_processed_files(log_folder, processed_files)
        print(f"Waiting for {SCAN_INTERVAL} seconds before next scan...")
        time.sleep(SCAN_INTERVAL)
