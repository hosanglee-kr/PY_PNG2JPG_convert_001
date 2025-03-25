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
    today = datetime.now()
    year_month = today.strftime("%Y%m")
    day = today.strftime("%Y%m%d")
    log_subfolder = os.path.join(log_folder, year_month)
    os.makedirs(log_subfolder, exist_ok=True)
    log_filename = os.path.join(log_subfolder, f"{base_folder_name}_error_{day}.log")
    logging.basicConfig(
        filename=log_filename,
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_processed_files_path(output_base_folder, base_folder_name, date_str):
    """날짜별 처리된 파일 목록 파일 경로를 생성합니다."""
    year_month = date_str[:6]  # YYYYMM 추출
    return os.path.join(output_base_folder, "mccb", base_folder_name, "Processed_files", year_month,
                        f"{base_folder_name}_{PROCESSED_FILES_PREFIX}{date_str}.txt")

def load_processed_files_from_file(output_base_folder, base_folder_name, target_date_str):
    """처리된 파일 목록을 파일에서 로드하여 전역 변수에 저장합니다."""
    global processed_files
    filepath = get_processed_files_path(output_base_folder, base_folder_name, target_date_str)
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
    else:
        processed_files = {} # 해당 날짜 처리 이력이 없으면 초기화

def save_processed_files_to_file(output_base_folder, base_folder_name, target_date_str):
    """현재 처리된 파일 목록을 파일에 저장합니다."""
    global processed_files
    filepath = get_processed_files_path(output_base_folder, base_folder_name, target_date_str)
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
        if not re.match(r'^\d{8}$', target_date_str):
            print("오류: 날짜 형식이 잘못되었습니다.<\ctrl3348>MMDD 형식으로 입력해주세요.")
            return
        try:
            target_date = datetime.strptime(target_date_str, "%Y%m%d").date()
        except ValueError:
            print("오류: 유효하지 않은 날짜 형식입니다.<\ctrl3348>MMDD 형식으로 입력해주세요.")
            return
    else:
        target_date = datetime.now().date()
        target_date_str = target_date.strftime("%Y%m%d")

    watch_folder = base_folder

    load_processed_files_from_file(output_base_folder, base_folder_name, target_date_str)

    print(f"[{base_folder_name}] 폴더 스캔 시작: {watch_folder} (날짜: {target_date_str})")
    for root, _, files in os.walk(watch_folder):
        for filename in files:
            if filename.lower().endswith(".png"):
                png_path = os.path.join(root, filename)
                relative_path = os.path.relpath(png_path, watch_folder)
                path_parts = relative_path.split(os.sep)

                if len(path_parts) == 4 and \
                   path_parts[0] in ['NG', 'OK', 'NG_OK'] and \
                   path_parts[1] == target_date.strftime("%Y%m") and \
                   path_parts[2] in ['LEFT', 'LINE', 'LINE_TAP', 'LOAD', 'LOAD_TAP', 'RIGHT', 'TOP']:

                    try:
                        modified_timestamp = os.path.getmtime(png_path)
                        modified_datetime = datetime.fromtimestamp(modified_timestamp)
                        modified_date = modified_datetime.date()

                        if modified_date == target_date:
                            if png_path not in processed_files or processed_files[png_path] != modified_timestamp:
                                print(f"[{base_folder_name}] 새로운 또는 수정된 PNG 발견 (날짜 일치): {png_path}")
                                if is_file_stable(png_path):
                                    convert_png_to_jpg(png_path, output_base_folder, base_folder, jpg_quality)
                                    save_processed_files_to_file(output_base_folder, base_folder_name, target_date_str)
                                else:
                                    print(f"[{base_folder_name}] PNG 파일이 아직 안정되지 않음: {png_path}")
                        elif modified_date > target_date:
                            # 과거 날짜 처리 후 현재 이후 날짜의 파일은 무시 (최적화)
                            continue

                    except Exception as e:
                        logging.error(f"파일 정보 가져오기 오류: {png_path} - {e}")

def main():
    """스크립트의 주요 실행 로직을 포함합니다."""
    parser = argparse.ArgumentParser(description="특정 Base 폴더의 PNG 이미지를 JPG로 변환합니다.")
    parser.add_argument("base_name", help="처리할 Base 폴더 이름 (config.ini에 정의).")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y%m%d"),
                        help="처리할 특정 날짜 (YYYYMMDD). 생략 시 오늘 날짜 처리.")


    #args = parser.parse_args()
    base_name = "ABH125c_1"
    base_name = base_name.lower()  

    #target_process_date = args.date
    target_process_date = datetime.now().strftime("%Y%m%d")


    config = load_config()
    output_base_folder = config['Paths']['output_base_folder']
    log_folder = config['Paths']['log_folder']
    setup_logging(log_folder, base_name)

    while True:
        find_and_process_png_files(config, base_name, target_process_date)
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()