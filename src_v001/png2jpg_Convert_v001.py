"""
이 스크립트는 특정 폴더를 감시하여 새로 생성되거나 수정된 PNG 이미지 파일을 JPG 형식으로 변환하는 프로그램입니다.

전체 처리 조직:

1.  **파일 시스템 감시 (watchdog):**
    -   watchdog 라이브러리를 사용하여 지정된 폴더를 감시하고, PNG 파일 생성 또는 수정 이벤트를 감지합니다.
    -   `PNGCreationHandler` 클래스는 파일 시스템 이벤트를 처리합니다.

2.  **작업 큐 (multiprocessing.Queue):**
    -   감지된 PNG 파일 경로는 `file_queue`라는 작업 큐에 추가됩니다.

3.  **작업 프로세스 (multiprocessing.Process):**
    -   여러 개의 작업 프로세스가 생성되어 `file_queue`에서 PNG 파일 경로를 가져와 실제로 이미지 변환 작업을 수행합니다.
    -   `convert_image` 함수는 각 작업 프로세스에서 실행됩니다.

4.  **처리된 파일 기록 (multiprocessing.Manager().Set()):**
    -   `processed_files` set은 이미 처리된 파일의 경로를 기록하여 중복 처리를 방지합니다.

5.  **로그 기록 (logging):**
    -   발생하는 에러 및 중요한 정보는 일자별 로그 파일에 기록됩니다.

처리 흐름:

1.  스크립트가 시작되면 설정된 폴더를 감시하기 시작합니다.
2.  새로운 PNG 파일이 생성되거나 수정되면 `PNGCreationHandler`에서 이를 감지합니다.
3.  감지된 파일이 안정적인 상태인지 확인 후 파일 경로를 `file_queue`에 넣습니다.
4.  미리 생성된 작업 프로세스들은 `file_queue`에서 파일 경로를 하나씩 가져와 `convert_image` 함수를 실행하여 JPG로 변환합니다.
5.  변환된 JPG 파일은 원본 PNG 파일의 날짜 정보를 기반으로 하는 하위 폴더에 저장됩니다.
6.  처리된 파일의 경로는 `processed_files` set에 기록됩니다.
7.  에러 발생 시 로그 파일에 관련 정보가 기록됩니다.
8.  스크립트는 계속해서 폴더를 감시하고 작업을 처리합니다.
"""
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
from multiprocessing import Process, Queue, Manager
import re
import sys
from datetime import datetime
import logging
import argparse
import configparser  # configparser 라이브러리 추가

GLOBAL_GRAYSCALE_MODE = None  # 전역 변수로 이미지 모드 저장 (True: 흑백, False: 컬러, None: 미결정)

def convert_image(input_path, output_base_folder, quality, queue):
    """
    개별 프로세스에서 이미지를 변환하는 함수입니다.
    원본 PNG의 흑백/컬러 모드를 유지하여 JPG로 변환합니다.

    Args:
        input_path (str): 변환할 PNG 파일의 전체 경로.
        output_base_folder (str): 변환된 JPG 파일을 저장할 최상위 폴더 경로.
        quality (int): JPG 이미지 품질 (0-100).
        queue (multiprocessing.Queue): 작업 완료 신호 전송을 위한 큐.
    """
    global GLOBAL_GRAYSCALE_MODE
    try:
        print(f"Process {os.getpid()}: Attempting to convert {input_path}")
        img = Image.open(input_path) # PNG 이미지 파일을 엽니다.
        input_dir = os.path.dirname(input_path) # 입력 파일의 부모 디렉토리 경로를 얻습니다.
        date_folder_name = os.path.basename(input_dir) # 부모 디렉토리 이름을 얻습니다 (YYYYMMDD 형식 가정).

        # 입력 폴더 이름에서 년월일 정보 추출 (정규표현식 사용)
        date_match = re.match(r'(\d{4})(\d{2})(\d{2})', date_folder_name)
        if date_match:
            year, month, day = date_match.groups() # 추출된 년, 월, 일을 튜플로 받습니다.
            output_folder = os.path.join(output_base_folder, year, month, day) # 출력 폴더 경로를 생성합니다.
            os.makedirs(output_folder, exist_ok=True) # 년월일 폴더를 생성합니다 (이미 존재하면 에러를 발생시키지 않습니다).
            filename, _ = os.path.splitext(os.path.basename(input_path)) # 입력 파일 이름에서 확장자를 제거합니다.
            temp_output_path = os.path.join(output_folder, f".temp_{filename}.jpg") # 임시 JPG 파일 경로를 생성합니다.
            final_output_path = os.path.join(output_folder, f"{filename}.jpg") # 최종 JPG 파일 경로를 생성합니다.

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
                    logging.warning(f"Process {os.getpid()}: Unknown image mode '{img.mode}' for {input_path}. Converting to RGB.")
                    img = img.convert('RGB') # 알 수 없는 모드의 경우 RGB로 변환합니다.
                    img.save(temp_output_path, "JPEG", quality=quality) # JPG 파일로 저장합니다.

            os.rename(temp_output_path, final_output_path) # 임시 파일 이름을 최종 파일 이름으로 변경합니다.
            print(f"Process {os.getpid()}: Converted {input_path} to {final_output_path} (Quality: {quality}, Mode: {'L' if GLOBAL_GRAYSCALE_MODE else 'RGB'})")
        else:
            logging.error(f"Process {os.getpid()}: Error - Could not extract date from folder name: {date_folder_name}, File: {input_path}")

    except FileNotFoundError:
        logging.error(f"Process {os.getpid()}: Error - Input file not found: {input_path}")
    except PermissionError:
        logging.error(f"Process {os.getpid()}: Error - Permission denied accessing file: {input_path} or {output_base_folder}")
    except Image.UnidentifiedImageError:
        logging.error(f"Process {os.getpid()}: Error - Could not open or read image file: {input_path}")
    except Exception as e:
        logging.error(f"Process {os.getpid()}: An unexpected error occurred during conversion of {input_path}: {e}")
    finally:
        queue.task_done() # 작업 완료를 큐에 알립니다.

class PNGCreationHandler(FileSystemEventHandler):
    """
    파일 시스템 이벤트 핸들러 클래스입니다.
    파일 생성 및 수정 이벤트를 감지하여 처리합니다.
    """
    def __init__(self, file_queue, output_base_folder):
        """
        생성자.

        Args:
            file_queue (multiprocessing.Queue): 처리할 파일 경로를 담는 큐.
            output_base_folder (str): 변환된 파일을 저장할 기본 출력 폴더 경로.
        """
        self.file_queue = file_queue
        self.stable_wait_time = 1 # 파일 안정성 확인 대기 시간 (초).
        self.output_base_folder = output_base_folder

    def process_image(self, file_path):
        """
        이미지 파일이 안정적인 상태인지 확인한 후 큐에 추가하는 로직입니다.

        Args:
            file_path (str): 처리할 이미지 파일의 경로.
        """
        try:
            initial_size = os.path.getsize(file_path) # 파일의 초기 크기를 얻습니다.
            time.sleep(self.stable_wait_time) # 잠시 대기합니다.
            current_size = os.path.getsize(file_path) # 파일의 현재 크기를 얻습니다.
            if initial_size == current_size and current_size > 0:
                self.file_queue.put(file_path) # 파일 크기가 변하지 않았고 0보다 크면 큐에 추가합니다.
                print(f"Detected stable PNG: {file_path} (Queue size: {self.file_queue.qsize()})")
            else:
                print(f"PNG file still being written or empty: {file_path}")
        except FileNotFoundError:
            logging.error(f"Error: File not found while checking stability: {file_path}")
        except PermissionError:
            logging.error(f"Error: Permission denied accessing file for stability check: {file_path}")
        except Exception as e:
            logging.error(f"Error during file stability check for {file_path}: {e}")

    def on_created(self, event):
        """
        파일 생성 이벤트 발생 시 호출됩니다.

        Args:
            event (watchdog.events.FileCreatedEvent): 파일 생성 이벤트 객체.
        """
        if not event.is_directory and event.src_path.lower().endswith(".png"):
            print(f"PNG file created: {event.src_path}")
            self.process_image(event.src_path) # 생성된 PNG 파일을 처리합니다.

    def on_modified(self, event):
        """
        파일 수정 이벤트 발생 시 호출됩니다.

        Args:
            event (watchdog.events.FileModifiedEvent): 파일 수정 이벤트 객체.
        """
        if not event.is_directory and event.src_path.lower().endswith(".png"):
            print(f"PNG file modified: {event.src_path}")
            self.process_image(event.src_path) # 수정된 PNG 파일을 처리합니다.

if __name__ == "__main__":
    # 설정 파일 읽기
    config = configparser.ConfigParser()
    config.read('config.ini')

    watch_base_folder = config['Paths']['watch_base_folder']
    output_base_folder = config['Paths']['output_base_folder']
    log_folder = config['Paths']['log_folder']
    jpg_quality = int(config['Image']['jpg_quality'])
    num_processes = int(config['Processing']['num_processes'])

    # 로그 폴더 생성
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    # 로그 파일 이름 설정 (일자별)
    today = datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(log_folder, f"error_{today}.log")

    # 로깅 설정
    logging.basicConfig(
        filename=log_filename,
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(processName)s - %(message)s'
    )

    # 명령행 인수를 처리하기 위한 ArgumentParser 생성
    parser = argparse.ArgumentParser(description="Convert PNG images to JPG.")
    parser.add_argument("date", nargs="?", help="Process folder for a specific date (YYYYMMDD). If not provided, processes today's date.")
    args = parser.parse_args()

    # 처리할 날짜 폴더 결정
    if args.date:
        target_date_str = args.date
        if re.match(r'^\d{8}$', target_date_str):
            watch_folder = os.path.join(watch_base_folder, target_date_str)
            print(f"Processing folder for date: {target_date_str} ({watch_folder})")
        else:
            print("Invalid date format. Please use 명령어: python your_script_name.py<0xE3><0x84><0xB3><0xE3><0x84><0xB9><0xE3><0x85><0xA7><0xE3><0x84><0x8F><0xE3><0x84><0x89>MMDD")
            sys.exit(1)
    else:
        now = datetime.now()
        target_date_str = now.strftime("%Y%m%d")
        watch_folder = os.path.join(watch_base_folder, target_date_str)
        print(f"Processing folder for today's date: {target_date_str} ({watch_folder})")

    GLOBAL_GRAYSCALE_MODE = None

    if os.path.exists(watch_folder):
        for filename in os.listdir(watch_folder):
            if filename.lower().endswith(".png"):
                first_png_path = os.path.join(watch_folder, filename)
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

        if GLOBAL_GRAYSCALE_MODE is None:
            print("No PNG files found to determine global color mode. Defaulting to color conversion.")
            GLOBAL_GRAYSCALE_MODE = False # 기본적으로 컬러로 설정
    else:
        print(f"Error: Watch folder does not exist: {watch_folder}")
        sys.exit(1)

    file_queue = Queue()

    # 멀티프로세싱 Manager를 생성합니다.
    manager = Manager()
    
    # Manager를 통해 프로세스 안전한 Set 객체를 생성합니다.
    processed_files = manager.list() # 수정된 부분
    #processed_files = manager.set() # 수정된 부분

    event_handler = PNGCreationHandler(file_queue, output_base_folder)
    observer = Observer()
    if os.path.exists(watch_folder):
        observer.schedule(event_handler, watch_folder, recursive=False) # 특정 날짜 폴더만 감시
        observer.start()

        # 스크립트 시작 시 미처리된 파일 처리 로직 (보완)
        print("Checking for unprocessed PNG files...")
        for filename in os.listdir(watch_folder):
            if filename.lower().endswith(".png"):
                png_path = os.path.join(watch_folder, filename)
                jpg_filename = os.path.splitext(filename)[0] + ".jpg"
                output_date_folder = os.path.join(output_base_folder, target_date_str[:4], target_date_str[4:6], target_date_str[6:])
                jpg_path = os.path.join(output_date_folder, jpg_filename)
                if not os.path.exists(jpg_path) and png_path not in processed_files:
                    print(f"Found unprocessed PNG: {png_path}")
                    try:
                        initial_size = os.path.getsize(png_path)
                        time.sleep(1)
                        current_size = os.path.getsize(png_path)
                        if initial_size == current_size and current_size > 0:
                            file_queue.put(png_path)
                            processed_files.append(png_path) # 수정된 부분
                            #processed_files.add(png_path)
                        else:
                            print(f"PNG file might be incomplete: {png_path}")
                    except Exception as e:
                        logging.error(f"Error checking unprocessed file: {e}")

        processes = []
        ##processes =
        for i in range(num_processes):
            process = Process(target=convert_image, args=(file_queue.get, output_base_folder, jpg_quality, file_queue))
            process.daemon = True
            processes.append(process)
            process.start()

        try:
            while observer.is_alive():
                observer.join(timeout=1)
                for i in range(len(processes)):
                    if not processes[i].is_alive() and not file_queue.empty():
                        process = Process(target=convert_image, args=(file_queue.get, output_base_folder, jpg_quality, file_queue))
                        process.daemon = True
                        processes.append(process)
                        process.start()

                # 주기적으로 감시 폴더를 다시 스캔하여 새로 생성되었지만 이벤트가 발생하지 않은 파일 처리 (보완)
                for filename in os.listdir(watch_folder):
                    if filename.lower().endswith(".png"):
                        png_path = os.path.join(watch_folder, filename)
                        jpg_filename = os.path.splitext(filename)[0] + ".jpg"
                        output_date_folder = os.path.join(output_base_folder, target_date_str[:4], target_date_str[4:6], target_date_str[6:])
                        jpg_path = os.path.join(output_date_folder, jpg_filename)
                        if not os.path.exists(jpg_path) and png_path not in processed_files:
                            print(f"Found potentially new unprocessed PNG: {png_path}")
                            try:
                                initial_size = os.path.getsize(png_path)
                                time.sleep(1)
                                current_size = os.path.getsize(png_path)
                                if initial_size == current_size and current_size > 0:
                                    file_queue.put(png_path)
                                    processed_files.append(png_path) # 수정된 부분
                                    #processed_files.add(png_path)
                                else:
                                    print(f"PNG file might be incomplete: {png_path}")
                            except Exception as e:
                                logging.error(f"Error checking potentially new unprocessed file: {e}")

        except KeyboardInterrupt:
            observer.stop()
        observer.join()

        file_queue.join()

        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join()

        print("Image conversion process finished.")
