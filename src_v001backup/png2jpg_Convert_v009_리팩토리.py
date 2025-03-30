import os
import time
from PIL import Image
import re
import sys
from datetime import datetime
import logging
import argparse
import configparser

# --- 설정 ---
CONFIG_FILE = '.\src_v001\config_v003.ini'
SCAN_INTERVAL = 1  # 폴더 스캔 간격 (초)
PROCESSED_FILES_PREFIX = "processed_files_"
PROCESSED_FILE_DELIMITER = "\t"

# --- 전역 변수 ---
processed_files = {}  # 처리된 파일 목록 (파일 경로: 최종 수정 시간)
GLOBAL_GRAYSCALE_MODE = None  # 이미지 모드 (True: 흑백, False: 컬러, None: 미결정)

# --- 함수 ---
def load_config():
    """설정 파일에서 설정을 로드합니다."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    return config

def setup_logging(log_folder, base_folder_name):
    """로깅을 설정합니다."""
    today = datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(log_folder, f"{base_folder_name}_error_{today}.log")
    logging.basicConfig(
        filename=log_filename,
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_processed_files_path(output_base_folder, base_folder_name, date_str=None):
    """날짜별 처리된 파일 목록 파일 경로를 생성합니다."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m")
    year_month = date_str
    return os.path.join(output_base_folder, "mccb", base_folder_name, "Processed_files", year_month,
                        f"{base_folder_name}_{PROCESSED_FILES_PREFIX}{date_str}.txt")

def load_processed_files_from_file(output_base_folder, base_folder_name):
    """처리된 파일 목록을 파일에서 로드하여 전역 변수에 저장합니다."""
    global processed_files
    today_str = datetime.now().strftime("%Y%m")
    filepath = get_processed_files_path(output_base_folder, base_folder_name, today_str)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split(PROCESSED_FILE_DELIMITER)
                    if len(parts) == 2:
                        file_path, timestamp = parts
                        processed_files[file_path] = float(timestamp)
        except Exception as e:
            logging.error(f"처리된 파일 목록 로드 중 오류 발생: {e}")

def save_processed_files_to_file(output_base_folder, base_folder_name):
    """현재 처리된 파일 목록을 파일에 저장합니다."""
    global processed_files
    today_str = datetime.now().strftime("%Y%m")
    filepath = get_processed_files_path(output_base_folder, base_folder_name, today_str)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    existing_data = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split(PROCESSED_FILE_DELIMITER)
                    if len(parts) == 2:
                        file_path, timestamp = parts
                        existing_data[file_path] = timestamp
        except Exception as e:
            logging.error(f"기존 처리된 파일 목록 읽기 중 오류 발생: {e}")

    updated_processed_dict = {}
    for file_path, timestamp in processed_files.items():
        if os.path.exists(file_path):
            try:
                current_modified_time = os.path.getmtime(file_path)
                updated_processed_dict[file_path] = current_modified_time
            except FileNotFoundError:
                logging.warning(f"처리된 목록 저장 중 파일을 찾을 수 없음: {file_path}")
            except Exception as e:
                logging.error(f"처리된 목록 저장 중 파일 수정 시간 가져오기 오류: {file_path} - {e}")
        else:
            logging.warning(f"처리된 목록에 파일 경로가 없음: {file_path}")

    for file_path, timestamp in updated_processed_dict.items():
        existing_data[file_path] = str(timestamp)  # 업데이트 또는 추가

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for file_path, timestamp in existing_data.items():
                f.write(f"{file_path}{PROCESSED_FILE_DELIMITER}{timestamp}\n")
            f.flush()
    except Exception as e:
        logging.error(f"처리된 파일 목록 쓰기 중 오류 발생: {e}")

def convert_png_to_jpg(input_path, output_base_folder, watch_base_folder, quality):
    """PNG 이미지를 JPG 형식으로 변환합니다."""
    global GLOBAL_GRAYSCALE_MODE
    global processed_files

    try:
        print(f"PNG 변환 시도: {input_path}")
        img = Image.open(input_path)

        relative_path = os.path.relpath(input_path, watch_base_folder)
        base_name = os.path.basename(watch_base_folder.rstrip('\\'))
        output_path = os.path.join(output_base_folder, "mccb", base_name, relative_path)
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)

        filename, _ = os.path.splitext(os.path.basename(input_path))
        temp_output_path = os.path.join(output_dir, f"{filename}.jpg.temp")
        final_output_path = os.path.join(output_dir, f"{filename}.jpg")

        for path in [temp_output_path, final_output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"기존 파일 삭제: {path}")
                except Exception as e:
                    logging.error(f"기존 파일 삭제 오류 {path}: {e}")
                    return

        if GLOBAL_GRAYSCALE_MODE is True:
            img = img.convert('L')
            img.save(temp_output_path, "JPEG", quality=quality)
        elif GLOBAL_GRAYSCALE_MODE is False:
            img = img.convert('RGB')
            img.save(temp_output_path, "JPEG", quality=quality)
        else:
            if img.mode == 'L':
                img.save(temp_output_path, "JPEG", quality=quality)
            elif img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
                img.save(temp_output_path, "JPEG", quality=quality)
            elif img.mode == 'RGB':
                img.save(temp_output_path, "JPEG", quality=quality)
            else:
                logging.warning(f"알 수 없는 이미지 모드 '{img.mode}': {input_path}. RGB로 변환합니다.")
                img = img.convert('RGB')
                img.save(temp_output_path, "JPEG", quality=quality)

        os.rename(temp_output_path, final_output_path)
        print(f"변환 완료: {input_path} → {final_output_path} (품질: {quality}, 모드: {'흑백' if GLOBAL_GRAYSCALE_MODE else '컬러'})")
        processed_files[input_path] = os.path.getmtime(input_path)
    except FileNotFoundError:
        logging.error(f"오류 - 입력 파일을 찾을 수 없음: {input_path}")
    except PermissionError:
        logging.error(f"오류 - 파일 접근 권한 거부: {input_path} 또는 {output_base_folder}")
    except Image.UnidentifiedImageError:
        logging.error(f"오류 - 이미지 파일을 열거나 읽을 수 없음: {input_path}")
    except Exception as e:
        logging.error(f"PNG 변환 중 예기치 않은 오류 발생: {input_path} - {e}")

def is_file_stable(file_path, wait_time=1):
    """파일이 완전히 쓰여졌는지 확인합니다."""
    try:
        initial_size = os.path.getsize(file_path)
        time.sleep(wait_time)
        current_size = os.path.getsize(file_path)
        return initial_size == current_size and current_size > 0
    except FileNotFoundError:
        logging.error(f"오류: 안정성 확인 중 파일을 찾을 수 없음: {file_path}")
        return False
    except PermissionError:
        logging.error(f"오류: 안정성 확인을 위한 파일 접근 권한 거부: {file_path}")
        return False
    except Exception as e:
        logging.error(f"파일 안정성 확인 중 오류 발생: {file_path} - {e}")
        return False

def find_and_process_png_files(config, base_name, target_date_str=None):
    """주어진 Base 폴더에서 PNG 파일을 찾아 변환합니다."""
    base_folders = dict(config.items('BaseFolders'))
    output_base_folder = config['Paths']['output_base_folder']
    jpg_quality = int(config['Image']['jpg_quality'])

    if base_name not in base_folders:
        print(f"오류: Base 폴더 이름 '{base_name}'이(가) config.ini [BaseFolders]에 없습니다.")
        return

    base_folder = base_folders[base_name]
    base_folder_name = base_name.lower()

    if target_date_str:
        now = datetime.now()
        target_yearMonth_str = now.strftime("%Y%m")

        if re.match(r'^\d{6}$', target_date_str):
            watch_folder = base_folder
            #print(f"[{base_folder_name}] {target_date_str} 폴더 처리 시작: {watch_folder}")
        else:
            print("오류: 날짜 형식이 잘못되었습니다. YYYYMM 형식으로 입력해주세요.")
            return
    else:
        now = datetime.now()
        target_yearMonth_str = now.strftime("%Y%m")
        watch_folder = base_folder
        #print(f"[{base_folder_name}] 오늘 날짜 폴더 처리 시작: {watch_folder}")

    load_processed_files_from_file(output_base_folder, base_folder_name)

    print(f"[{base_folder_name}] 폴더 스캔 시작: {watch_folder}")
    for root, folders, files in os.walk(watch_folder):
        for folder in folders:
            if folder in ['NG', 'OK', 'NG_OK']:
                folder_yearMonth = os.path.join(watch_folder, folder, target_yearMonth_str)
                if not os.path.exists(folder_yearMonth):
                    continue
                for sub_root, folder_yearMonth_sides, sub_files in os.walk(folder_yearMonth):
                    for folder_side in folder_yearMonth_sides:
                        if folder_side in ['LEFT', 'LINE', 'LINE_TAP', 'LOAD', 'LOAD_TAP', 'RIGHT', 'TOP']:
                            folder_yearMonth_side = os.path.join(folder_yearMonth, folder_side)
                            if not os.path.exists(folder_yearMonth_side):
                                continue
                            for sub_sub_root, _, sub_files in os.walk(folder_yearMonth_side):
                                for filename in sub_files:
                                    if filename.lower().endswith(".png"):
                                        png_path = os.path.join(sub_sub_root, filename)
                                        current_modified_time = os.path.getmtime(png_path)

                                        if png_path not in processed_files or processed_files[png_path] != current_modified_time:
                                            print(f"[{base_folder_name}] 새로운 또는 수정된 PNG 발견: {png_path}")
                                            if is_file_stable(png_path):
                                                convert_png_to_jpg(png_path, output_base_folder, base_folder, jpg_quality)
                                                save_processed_files_to_file(output_base_folder, base_folder_name)
                                            else:
                                                print(f"[{base_folder_name}] PNG 파일이 아직 안정되지 않음: {png_path}")

def main():
    """스크립트의 주요 실행 로직을 포함합니다."""
    parser = argparse.ArgumentParser(description="특정 Base 폴더의 PNG 이미지를 JPG로 변환합니다.")
    parser.add_argument("base_name", help="처리할 Base 폴더 이름 (config.ini에 정의).")
    parser.add_argument("date", nargs="?", help="특정 날짜 폴더 처리 (YYYYMM). 생략 시 오늘 날짜 처리.")

    #args = parser.parse_args()
    base_name = "ABH125c_1"
    base_name = base_name.lower()  

    #today_yearMonth = args.date
    today_yearMonth = datetime.now().strftime("%Y%m")

    config = load_config()
    output_base_folder = config['Paths']['output_base_folder']
    log_folder = config['Paths']['log_folder']
    setup_logging(log_folder, base_name)

    while True:
        find_and_process_png_files(config, base_name, today_yearMonth)
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()
