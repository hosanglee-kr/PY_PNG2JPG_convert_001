import os
import time
import re
import sys
from datetime import datetime
import logging
import argparse
import configparser
import multiprocessing
import asyncio
import aiofiles
import aiofiles.os as aos
import cv2  # OpenCV import

# --- 전체 처리 기능 ---
# 1. 설정 파일(config_v003.ini)을 로드하여 프로그램 동작에 필요한 경로, 간격, 품질 등의 설정을 읽어옵니다.
# 2. 지정된 Base 폴더를 지속적으로 감시하며, 새로운 PNG 이미지 파일 또는 수정된 PNG 이미지 파일을 찾습니다.
# 3. 찾은 PNG 이미지 파일이 특정 폴더 구조 규칙 (NG, OK, NG_OK 폴더 하위의 연월 폴더, 그 하위의 LEFT, LINE 등 폴더)과 파일명 규칙을 따르는지 확인합니다.
# 4. 이미지 파일이 완전히 쓰여져서 안정적인 상태인지 확인합니다.
# 5. PNG 이미지를 JPG 형식으로 변환하고, 설정된 품질로 저장합니다.
# 6. 변환된 JPG 파일은 원본 PNG 파일의 경로 구조를 유지하며, output_base_folder 아래에 저장됩니다.
# 7. 이미 처리된 파일 목록을 관리하여 중복 처리를 방지합니다. 처리된 파일 정보는 날짜별 텍스트 파일로 저장됩니다.
# 8. 에러 발생 시 로그 파일에 기록합니다.
# 9. 특정 날짜의 파일만 처리하는 기능을 제공합니다 (명령행 인자 또는 기본값으로 오늘 날짜).
# 10. 이미지 모드 설정을 통해 흑백 또는 컬러 JPG로 변환할 수 있습니다.

# --- 기능 요구사항 ---
# - 설정 파일에서 감시 폴더, 출력 폴더, 로그 폴더, JPG 품질 등의 설정을 관리해야 합니다.
# - 특정 간격으로 폴더를 스캔하여 새로운 또는 수정된 PNG 파일을 감지해야 합니다.
# - 처리된 파일 목록을 유지하여 동일한 파일을 반복해서 처리하지 않아야 합니다.
# - PNG 파일을 JPG 형식으로 변환하고 지정된 품질로 저장해야 합니다.
# - 원본 파일의 폴더 구조를 유지하며 변환된 파일을 저장해야 합니다.
# - 파일이 완전히 쓰여진 후에만 변환을 시도해야 합니다.
# - 에러 발생 시 상세한 로그를 기록해야 합니다.
# - 특정 날짜의 파일만 처리할 수 있는 옵션을 제공해야 합니다.
# - 흑백 또는 컬러 변환 옵션을 제공해야 합니다.

# --- 설정 ---
CONFIG_FILE = r'.\src_v001\config_v003.ini'
SCAN_INTERVAL = 1  # 폴더 스캔 간격 (초)
PROCESSED_FILES_PREFIX = "processed_files_"
PROCESSED_FILE_DELIMITER = "\t"

# --- 함수 ---
async def load_config():
    """설정 파일에서 설정을 로드하고 이미지 모드를 반환합니다."""
    config = configparser.ConfigParser()
    global_grayscale_mode = None
    try:
        async with aiofiles.open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
        config.read_string(content)
        if 'Image' in config and 'image_mode' in config['Image']:
            image_mode = config['Image']['image_mode'].lower()
            if image_mode == 'grayscale':
                global_grayscale_mode = True
            elif image_mode == 'color':
                global_grayscale_mode = False
            else:
                print(f"경고: 설정 파일의 'image_mode' 값이 잘못되었습니다. (grayscale 또는 color). 기본 설정(자동)으로 유지합니다.")
        else:
            print("경고: 설정 파일에 [Image] 섹션 또는 'image_mode' 설정이 없습니다. 기본 설정(자동)으로 유지합니다.")
        return config, global_grayscale_mode
    except FileNotFoundError:
        print(f"오류: 설정 파일 '{CONFIG_FILE}'을 찾을 수 없습니다.")
        sys.exit(1)
    except configparser.Error as e:
        print(f"오류: 설정 파일 '{CONFIG_FILE}'을 읽는 동안 오류가 발생했습니다: {e}")
        sys.exit(1)

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
    year_month = date_str[:6]  #<\ctrl3348>MM 추출
    return os.path.join(output_base_folder, "mccb", base_folder_name, "Processed_files", year_month,
                        f"{base_folder_name}_{PROCESSED_FILES_PREFIX}{date_str}.txt")

async def load_processed_files_from_file(output_base_folder, base_folder_name, target_date_str):
    """처리된 파일 목록을 파일에서 비동기적으로 로드하여 반환합니다."""
    processed_files = {}
    filepath = get_processed_files_path(output_base_folder, base_folder_name, target_date_str)
    try:
        if await aos.path.exists(filepath):
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                async for line in f:
                    parts = line.strip().split(PROCESSED_FILE_DELIMITER)
                    if len(parts) == 2:
                        file_path, timestamp = parts
                        processed_files[file_path] = float(timestamp)
    except Exception as e:
        logging.error(f"처리된 파일 목록 로드 중 오류 발생: {e}")
    return processed_files

async def save_processed_files_to_file(output_base_folder, base_folder_name, target_date_str, processed_files):
    """현재 처리된 파일 목록을 파일에 비동기적으로 저장합니다."""
    filepath = get_processed_files_path(output_base_folder, base_folder_name, target_date_str)
    await aos.makedirs(os.path.dirname(filepath), exist_ok=True)

    existing_data = await load_processed_files_from_file(output_base_folder, base_folder_name, target_date_str)
    updated_processed_dict = {}

    for file_path, timestamp in processed_files.items():
        try:
            if await aos.path.exists(file_path):
                stat_result = await aos.stat(file_path)
                current_modified_time = stat_result.st_mtime
                updated_processed_dict[file_path] = current_modified_time
            else:
                logging.warning(f"처리된 목록 저장 중 파일을 찾을 수 없음: {file_path}")
        except Exception as e:
            logging.error(f"처리된 목록 저장 중 파일 정보 가져오기 오류: {file_path} - {e}")

    for file_path, timestamp in updated_processed_dict.items():
        existing_data[file_path] = str(timestamp)  # 업데이트 또는 추가

    try:
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            for file_path, timestamp in existing_data.items():
                await f.write(f"{file_path}{PROCESSED_FILE_DELIMITER}{timestamp}\n")
    except Exception as e:
        logging.error(f"처리된 파일 목록 쓰기 중 오류 발생: {e}")

def convert_png_to_jpg_single(input_path, output_base_folder, watch_base_folder, quality, global_grayscale_mode):
    """PNG 이미지를 JPG 형식으로 변환하는 단일 프로세스 함수입니다 (OpenCV 사용)."""
    try:
        print(f"PNG 변환 시도 (Process {multiprocessing.current_process().name}): {input_path}")
        img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)

        if img is None:
            logging.error(f"오류 - OpenCV로 이미지 읽기 실패: {input_path}")
            return None, None

        output_img = None
        if global_grayscale_mode is True:
            if len(img.shape) == 3 and img.shape[2] == 4:  # RGBA
                # Convert RGBA to RGB (remove alpha)
                rgb_img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                output_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2GRAY)
            elif len(img.shape) == 3:  # 컬러 (BGR 기본)
                output_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:  # 이미 흑백
                output_img = img
        elif global_grayscale_mode is False:
            if len(img.shape) == 4:  # RGBA
                output_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
            elif len(img.shape) == 3:  # 컬러 (BGR 기본)
                output_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            else:  # 흑백을 RGB로 변환
                output_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:  # 자동 모드
            if len(img.shape) == 4:  # RGBA
                output_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
            elif len(img.shape) == 3:  # 컬러 (BGR 기본)
                output_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            else:  # 흑백
                output_img = img

        relative_path = os.path.relpath(input_path, watch_base_folder)
        base_name = os.path.basename(watch_base_folder.rstrip('\\'))
        output_path = os.path.join(output_base_folder, r"mccb", base_name, relative_path) # raw string 적용
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)

        filename, _ = os.path.splitext(os.path.basename(input_path))
        temp_output_path = os.path.join(output_dir, f"{filename}.jpg.temp")
        final_output_path = os.path.join(output_dir, f"{filename}.jpg")

        for path in [temp_output_path, final_output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"기존 파일 삭제 (Process {multiprocessing.current_process().name}): {path}")
                except Exception as e:
                    logging.error(f"기존 파일 삭제 오류 (Process {multiprocessing.current_process().name}) {path}: {e}")
                    return None, None

        if output_img is not None:
            cv2.imwrite(temp_output_path, output_img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            os.rename(temp_output_path, final_output_path)
            print(f"변환 완료 (Process {multiprocessing.current_process().name}): {input_path} → {final_output_path} (품질: {quality}, 모드: {'흑백' if global_grayscale_mode else '컬러'})")
            return input_path, os.path.getmtime(input_path)
        else:
            logging.error(f"오류 - 이미지 변환 실패: {input_path}")
            return None, None

    except Exception as e:
        logging.error(f"PNG 변환 중 예기치 않은 오류 발생 (Process {multiprocessing.current_process().name}): {input_path} - {e}")
    return None, None

async def is_file_stable(file_path, wait_time=1):
    """파일이 완전히 쓰여졌는지 비동기적으로 확인합니다."""
    try:
        initial_size = await aos.path.getsize(file_path)
        await asyncio.sleep(wait_time)
        current_size = await aos.path.getsize(file_path)
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

async def find_and_process_png_files(config, base_name, target_date_str, processed_files, global_grayscale_mode, num_processes):
    """주어진 Base 폴더에서 PNG 파일을 찾아 병렬로 변환합니다 (비동기 I/O 사용)."""
    base_folders = dict(config.items('BaseFolders'))
    output_base_folder = config['Paths']['output_base_folder']
    jpg_quality = int(config['Image']['jpg_quality'])

    if base_name not in base_folders:
        print(f"오류: Base 폴더 이름 '{base_name}'이(가) config.ini [BaseFolders]에 없습니다.")
        return processed_files

    base_folder = base_folders[base_name]
    base_folder_name = base_name.lower()

    if target_date_str:
        if not re.match(r'^\d{8}$', target_date_str):
            print("오류: 날짜 형식이 잘못되었습니다.<\ctrl3348>MMDD 형식으로 입력해주세요.")
            return processed_files
        try:
            target_date = datetime.strptime(target_date_str, "%Y%m%d").date()
        except ValueError:
            print("오류: 유효하지 않은 날짜 형식입니다.<\ctrl3348>MMDD 형식으로 입력해주세요.")
            return processed_files
    else:
        target_date = datetime.now().date()
        target_date_str = target_date.strftime("%Y%m%d")

    watch_folder = base_folder

    current_processed_files = await load_processed_files_from_file(output_base_folder, base_folder_name, target_date_str)

    png_files_to_process = []

    print(f"[{base_folder_name}] 폴더 스캔 시작: {watch_folder} (날짜: {target_date_str})")
    for root, _, files in await asyncio.to_thread(os.walk, watch_folder):
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
                        stat_result = await aos.stat(png_path)
                        modified_timestamp = stat_result.st_mtime
                        modified_datetime = datetime.fromtimestamp(modified_timestamp)
                        modified_date = modified_datetime.date()

                        if modified_date == target_date:
                            if png_path not in current_processed_files or current_processed_files[png_path] != modified_timestamp:
                                print(f"[{base_folder_name}] 새로운 또는 수정된 PNG 발견 (날짜 일치): {png_path}")
                                if await is_file_stable(png_path):
                                    png_files_to_process.append(png_path)
                                else:
                                    print(f"[{base_folder_name}] PNG 파일이 아직 안정되지 않음: {png_path}")
                            elif modified_date > target_date:
                                # 과거 날짜 처리 후 현재 이후 날짜의 파일은 무시 (최적화)
                                continue

                    except Exception as e:
                        logging.error(f"파일 정보 가져오기 오류: {png_path} - {e}")

    if png_files_to_process:
        print(f"[{base_folder_name}] 발견된 {len(png_files_to_process)}개의 PNG 파일을 병렬 처리 시작 (프로세스 수: {num_processes}).")
        with multiprocessing.Pool(processes=num_processes) as pool:
            tasks = [(png_file, output_base_folder, watch_folder, jpg_quality, global_grayscale_mode) for png_file in png_files_to_process]
            results = pool.starmap(convert_png_to_jpg_single, tasks)

            for input_path, modified_time in results:
                if input_path:
                    processed_files[input_path] = modified_time
        await save_processed_files_to_file(output_base_folder, base_folder_name, target_date_str, processed_files)
    else:
        print(f"[{base_folder_name}] 처리할 새로운 또는 수정된 PNG 파일 없음 (날짜: {target_date_str}).")

    return processed_files

async def main():
    """스크립트의 주요 실행 로직을 포함합니다 (비동기 버전)."""
    parser = argparse.ArgumentParser(description="특정 Base 폴더의 PNG 이미지를 JPG로 변환합니다 (멀티프로세싱 및 비동기 I/O 지원).")
    parser.add_argument("base_name", help="처리할 Base 폴더 이름 (config.ini에 정의).")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y%m%d"),
                        help="처리할 특정 날짜 (YYYYMMDD). 생략 시 오늘 날짜 처리.")
    parser.add_argument("-p", "--processes", type=int, default=4,
                        help="사용할 병렬 프로세스 수 (기본값: 4).")

    args = parser.parse_args()
    base_name = args.base_name.lower()
    target_process_date = args.date
    num_processes = args.processes

    config, global_grayscale_mode = await load_config()
    output_base_folder = config['Paths']['output_base_folder']
    log_folder = config['Paths']['log_folder']
    setup_logging(log_folder, base_name)

    processed_files = {}

    while True:
        processed_files = await find_and_process_png_files(config, base_name, target_process_date, processed_files, global_grayscale_mode, num_processes)
        await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    # multiprocessing.freeze_support() # Windows에서 PyInstaller 등으로 패키징할 때 필요할 수 있습니다.
    asyncio.run(main())
