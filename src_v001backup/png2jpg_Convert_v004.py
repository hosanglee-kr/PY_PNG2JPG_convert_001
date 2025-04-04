# 이 스크립트는 특정 폴더를 주기적으로 감시하여 새로 생성되거나 수정된 PNG 이미지 파일을 JPG 형식으로 변환하는 프로그램입니다.
# Samba 공유 폴더 환경을 고려하여 watchdog 대신 폴더 스캔 방식을 사용하며, 멀티프로세싱을 제거하여 단일 프로세스로 동작합니다.
# JPG 저장 폴더 구조는 원본 PNG 파일과 동일한 구조를 유지하며, 프로세스 재실행 시에도 문제없이 동작합니다.
# 변환된 JPG 파일은 다른 프로그램에서 5분에 한번씩 다른 폴더로 이동될 수 있는 환경을 고려하여 처리 로직을 개선했습니다.
# 처리된 PNG 파일 목록은 날짜별 파일에 저장됩니다.
# 설정 파일(`config.ini`)에 원본 Base 폴더 경로를 설정하고, 파라미터로 Base 폴더 이름을 지정하여 실행할 수 있도록 수정되었습니다.
#
# **주요 기능:**
#
# 1.  **주기적인 폴더 스캔:** 설정 파일에 정의된 원본 Base 폴더 중 명령행 인자로 지정된 이름에 해당하는 폴더 아래의 날짜별 폴더를 지정된 시간 간격으로 검색하여 PNG 파일을 찾습니다.
# 2.  **PNG → JPG 변환:** 발견된 PNG 파일을 Pillow 라이브러리를 사용하여 JPG 형식으로 변환합니다.
# 3.  **지정된 폴더 구조로 JPG 저장:** 변환된 JPG 파일은 설정 파일에 지정된 `output_base_folder` 아래에 `mccb/<Base 폴더 이름>/<원본 하위 폴더 구조>` 형태로 저장합니다.
# 4.  **흑백/컬러 모드 유지:** 원본 PNG 파일의 흑백 또는 컬러 모드를 유지하여 JPG로 변환합니다.
# 5.  **처리된 파일 기록:** 처리된 PNG 파일의 경로는 `<output_base_folder>/mccb/<Base 폴더 이름>/Processed_files/YYYYMM/` 경로에 날짜별 파일로 저장하여 스크립트 재실행 시 중복 처리를 방지합니다. 처리된 파일 목록은 Base 폴더 이름별로 관리됩니다.
# 6.  **파일 안정성 확인:** 변환 전에 PNG 파일이 완전히 쓰여졌는지 확인하여 불완전한 파일 변환을 방지합니다.
# 7.  **로그 기록:** 발생하는 에러는 Base 폴더 이름별, 일자별 로그 파일에 기록하여 문제 발생 시 추적을 용이하게 합니다.
# 8.  **명령행 인자 처리:** 처리할 Base 폴더의 이름 (설정 파일에 정의된 키 값) 및 특정 날짜 (선택 사항)를 명령행 인자로 지정할 수 있습니다.
# 9.  **설정 파일 사용:** 출력 폴더 (`output_base_folder`), 로그 폴더 (`log_folder`), JPG 품질 (`jpg_quality`), 원본 Base 폴더 경로를 외부 설정 파일(`config.ini`)에서 공통으로 관리합니다.
# 10. **외부 파일 이동 고려:** 변환된 JPG 파일이 외부 프로그램에 의해 이동될 수 있는 상황을 고려하여 처리 로직을 개선했습니다.
# 11. **다중 Base 폴더 지원:** 설정 파일과 명령행 인자를 통해 처리할 Base 폴더를 지정하여 독립적인 실행이 가능합니다.
#
# **실행 방법:**
#
# 각각의 원본 Base 폴더에 대해 별도의 터미널을 열고 스크립트를 실행합니다.
# Base 폴더 이름은 `config.ini` 파일의 `[BaseFolders]` 섹션에 정의된 키 값으로 지정합니다.
#
# ```bash
# python your_script_name.py ABH125c_1 202503
# python your_script_name.py ABH125c_2 202503
# python your_script_name.py ABH125c_3 202503
# ```
#
# 위 명령어에서 `your_script_name.py`는 실제 스크립트 파일 이름으로 변경해야 합니다.
# Base 폴더 이름 (`ABH125c_1`, `ABH125c_2`, `ABH125c_3`)은 첫 번째 파라미터로 전달합니다.
# 날짜 인수로 `202503`을 제공하면 해당 월의 하위 폴더를 검색하여 PNG 파일을 처리합니다.
# 오늘 날짜의 폴더를 처리하려면 날짜 인수를 생략할 수 있습니다.
#
# ```bash
# python your_script_name.py ABH125c_1
# ```
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
SCAN_INTERVAL = 5  # 폴더 스캔 간격 (초)
PROCESSED_FILES_PREFIX = "processed_files_" # 처리된 파일 목록 파일명 접두사


CONFIG_FILE = '.\src_v001\config_v003.ini'


def get_processed_files_filename(output_base_folder, base_folder_name, date_str=None):
    """날짜별 처리된 파일 목록 파일 이름을 생성합니다."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m")
    year_month = date_str

    
    return os.path.join(output_base_folder, "mccb", base_folder_name, "Processed_files", year_month, f"{base_folder_name}_{PROCESSED_FILES_PREFIX}{date_str}.txt")

def load_processed_files(output_base_folder, base_folder_name):
    """오늘 날짜의 처리된 파일 목록을 파일에서 로드합니다."""
    today_str = datetime.now().strftime("%Y%m")
    filepath = get_processed_files_filename(output_base_folder, base_folder_name, today_str)
    processed = set()
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            for line in f:
                processed.add(line.strip())
    return processed

def save_processed_files(output_base_folder, base_folder_name, processed_set):
    """오늘 날짜의 처리된 파일 목록을 파일에 저장합니다."""
    today_str = datetime.now().strftime("%Y%m")
    filepath = get_processed_files_filename(output_base_folder, base_folder_name, today_str)
    os.makedirs(os.path.dirname(filepath), exist_ok=True) # 폴더가 없으면 생성
    with open(filepath, 'w') as f:
        for item in processed_set:
            f.write(f"{item}\n")

def convert_image(input_path, output_base_folder, watch_base_folder, quality, processed_files):
    """
    단일 프로세스에서 이미지를 변환하는 함수입니다.
    원본 PNG의 흑백/컬러 모드를 유지하여 JPG로 변환합니다.
    JPG 저장 폴더 구조는 지정된 규칙을 따릅니다.

    Args:
        input_path (str): 변환할 PNG 파일의 전체 경로.
        output_base_folder (str): 변환된 JPG 파일을 저장할 최상위 폴더 경로 (예: '..\Output').
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
        # 출력 경로를 지정된 구조로 생성합니다.
        base_name = os.path.basename(watch_base_folder.rstrip('\\')) # watch_base_folder에서 base 이름 추출
        output_path = os.path.join(output_base_folder, "mccb", base_name, relative_path)
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
    config.read(CONFIG_FILE, encoding='utf-8')
    

    # 설정 파일에서 출력 폴더, 로그 폴더, JPG 품질 설정을 읽어옵니다.
    output_base_folder = config['Paths']['output_base_folder']
    log_folder = config['Paths']['log_folder']
    jpg_quality = int(config['Image']['jpg_quality'])

    # Base 폴더 설정 읽어오기
    base_folders = dict(config.items('BaseFolders'))

    # 로그 폴더가 존재하지 않으면 생성합니다.
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    # 명령행 인수를 처리하기 위한 ArgumentParser를 생성합니다.
    parser = argparse.ArgumentParser(description="Convert PNG images to JPG for a specific base folder.")
    parser.add_argument("base_name", help="The name of the base folder to process (defined in config.ini).")
    parser.add_argument("date", nargs="?", help="Process folder for a specific date (YYYYMM). If not provided, processes today's month.")
    #### args = parser.parse_args() # 명령행 인수를 파싱합니다.

    base_name = "ABH125c_1"
    base_name = base_name.lower()  

    ### base_name = args.base_name
    if base_name not in base_folders:
        print(f"Error: Base folder name '{base_name}' not found in config.ini [BaseFolders].")
        sys.exit(1)


    base_folder = base_folders[base_name]
    base_folder_name = base_name # 명령행 인자로 받은 base 이름을 그대로 사용

    # 로그 파일 이름을 base 폴더 이름과 현재 날짜를 기반으로 설정합니다 (ABH125c_1_error_YYYYMMDD.log 형식).
    today = datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(log_folder, f"{base_folder_name}_error_{today}.log")

    # 로깅 설정을 구성합니다. 에러 메시지를 로그 파일에 기록하고, 메시지 형식과 로그 레벨을 설정합니다.
    logging.basicConfig(
        filename=log_filename,
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    #target_date_str = args.date 
    temp_target_date_str = None

    # 처리할 날짜 폴더 결정
    if temp_target_date_str:
        target_date_str = temp_target_date_str
        # 입력된 날짜 형식이YYYYMM인지 정규표현식으로 확인합니다.
        if re.match(r'^\d{6}$', target_date_str): # 날짜 형식을YYYYMM으로 변경
            watch_folder = os.path.join(base_folder, target_date_str)
            print(f"Processing folder for base: {base_folder}, date: {target_date_str} ({watch_folder})")
        else:
            print("Invalid date format. Please use 명령어: python your_script_name.py <base_name> YYYYMM")
            sys.exit(1)
    else:
        # 명령행 인자로 날짜가 제공되지 않은 경우, 현재 날짜를 기준으로 처리할 폴더를 설정합니다.
        now = datetime.now()
        target_yearMonth_str = now.strftime("%Y%m") # 현재 날짜를YYYYMM 형식으로 변경
        watch_folder = base_folder
        #watch_folder = os.path.join(base_folder, target_date_str)
        print(f"Processing folder for base: {base_folder}, today's date: ({watch_folder})")

    # 오늘 날짜의 처리된 파일 목록을 로드합니다 (base 폴더 이름 포함).
    processed_files = load_processed_files(output_base_folder, base_folder_name)

    # 무한 루프를 시작하여 폴더를 주기적으로 스캔하고 PNG 파일을 처리합니다.
    while True:

        
        # 감시 대상 폴더가 실제로 존재하는지 확인합니다.
        ##if os.path.exists(watch_folder):
        
        # 스크립트 시작 시 또는 주기적인 스캔 시 global grayscale mode를 결정합니다.
        GLOBAL_GRAYSCALE_MODE = False       ## img.mode == 'P' 임

        # # 감시 폴더 및 하위 폴더를 순회하며 PNG 파일을 찾습니다.
        # for root, folders, files in os.walk(watch_folder):
        #     # 특정 하위 폴더만 처리하도록 필터링
        #     for folder in folders:
        #         if folder in ['NG', 'OK', 'NG_OK']: # NG, OK, NG_OK 폴더만 확인
        #             folder_yearMonth = os.path.join(watch_folder, folder, target_yearMonth_str)
        #             for sub_root, folder_yearMonth_sides, sub_files in os.walk(folder_yearMonth):
        #                 for folder_side in folder_yearMonth_sides:
        #                     if folder_side in ['LEFT', 'LINE', 'LINE_TAP', 'LOAD', 'LOAD_TAP', 'RIGHT', 'TOP']:
        #                         folder_yearMonth_side = os.path.join(folder_yearMonth, folder_side)
        #                         for sub_sub_root, _, sub_files in os.walk(folder_yearMonth_side):
        #                             for filename in sub_files:
        #                                 if filename.lower().endswith(".png"):
        #                                     first_png_path = os.path.join(sub_root, folder_side, filename)
        #                                     try:
        #                                         with Image.open(first_png_path) as img:
        #                                             if img.mode == 'L':
        #                                                 GLOBAL_GRAYSCALE_MODE = True
        #                                                 print(f"[{base_folder_name}] Detected grayscale mode for all images.")
        #                                             else:
        #                                                 GLOBAL_GRAYSCALE_MODE = False
        #                                                 print(f"[{base_folder_name}] Detected color mode for all images.")
        #                                             break  # 첫 번째 PNG 파일만 확인
        #                                     except Exception as e:
        #                                         logging.error(f"[{base_folder_name}] Error opening first PNG file for mode detection: {first_png_path} - {e}")
        #                                 if GLOBAL_GRAYSCALE_MODE is not None:
        #                                     break
        #     if GLOBAL_GRAYSCALE_MODE is not None:
        #         break

        # if GLOBAL_GRAYSCALE_MODE is None:
        #     print(f"[{base_folder_name}] No PNG files found to determine global color mode. Defaulting to color conversion.")
        #     GLOBAL_GRAYSCALE_MODE = False # 기본적으로 컬러로 설정

        print(f"[{base_folder_name}] Scanning folder: {watch_folder}")
        # 감시 폴더 및 하위 폴더를 순회하며 PNG 파일을 찾습니다.
        for root, folders, files in os.walk(watch_folder):
            for folder in folders:    
                # NG, OK, NG_OK 폴더만 확인
                if folder in ['NG', 'OK', 'NG_OK']: # NG, OK, NG_OK 폴더만 확인
                    folder_yearMonth = os.path.join(watch_folder, folder, target_yearMonth_str)
                    for sub_root, folder_yearMonth_sides, sub_files in os.walk(folder_yearMonth):
                        for folder_side in folder_yearMonth_sides:
                            if folder_side in ['LEFT', 'LINE', 'LINE_TAP', 'LOAD', 'LOAD_TAP', 'RIGHT', 'TOP']:
                                folder_yearMonth_side = os.path.join(folder_yearMonth, folder_side)
                                for sub_sub_root, _, sub_files in os.walk(folder_yearMonth_side):
                                    for filename in sub_files:
                                        if filename.lower().endswith(".png"):

                                            png_path = os.path.join(sub_sub_root, filename)
                                            relative_path = os.path.relpath(png_path, base_folder) # base_folder 기준으로 상대 경로 생성
                                            output_path = os.path.join(output_base_folder, "mccb", base_name, relative_path.replace(".png", ".jpg"))

                                            # 아직 처리되지 않았고, JPG 파일이 존재하지 않는 경우
                                            if png_path not in processed_files and not os.path.exists(output_path):
                                                print(f"[{base_folder_name}] Found potentially new PNG: {png_path}")
                                                # 파일이 안정적인 상태인지 확인 후 변환을 시도합니다.
                                                if is_stable(png_path):
                                                    convert_image(png_path, output_base_folder, base_folder, jpg_quality, processed_files)
                                                else:
                                                    print(f"[{base_folder_name}] PNG file not yet stable: {png_path}")
                                            # 이미 처리된 파일 목록에 있지만, JPG 파일이 없는 경우 (이전 실행 실패 또는 JPG 파일이 이동되었을 수 있음) 다시 변환을 시도합니다.
                                            elif png_path in processed_files and not os.path.exists(output_path):
                                                print(f"[{base_folder_name}] Re-converting (JPG missing): {png_path}")
                                                if is_stable(png_path):
                                                    convert_image(png_path, output_base_folder, base_folder, jpg_quality, processed_files)
                                                else:
                                                    print(f"[{base_folder_name}] PNG file not yet stable: {png_path}")
                                            # JPG 파일이 이미 존재하고, processed_files에 없는 경우 (이전 실행에서 처리됨) processed_files에 추가합니다.
                                            elif os.path.exists(output_path) and png_path not in processed_files:
                                                processed_files.add(png_path)
                                                print(f"[{base_folder_name}] PNG already processed (JPG exists): {png_path}")

        # 현재 처리된 파일 목록을 오늘 날짜의 파일에 저장합니다 (base 폴더 이름 포함).
        save_processed_files(output_base_folder, base_folder_name, processed_files)
        print(f"[{base_folder_name}] Waiting for {SCAN_INTERVAL} seconds before next scan...")
        time.sleep(SCAN_INTERVAL)
