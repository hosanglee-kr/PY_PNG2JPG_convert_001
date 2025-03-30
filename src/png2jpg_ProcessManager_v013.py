# 프로그램 2 (manager_with_full_monitor.py)
#
# 기능:
#     - 설정된 프로그램 1 (png2jpg_Convert_v013.py 또는 png2jpg_Convert_v013.exe)을 지정된 argument 리스트에 따라 여러 개 실행하고 관리합니다.
#     - 각 프로그램 1 인스턴스의 실행 상태를 주기적으로 (기본 10초) 확인하고, 작동이 중단된 경우 자동으로 재실행합니다.
#     - 활성화된 경우 (G_ENABLE_MONITORING = True), 각 프로그램 1 인스턴스의 CPU 사용량, 메모리 사용량, 디스크 I/O 사용량 및 시스템 전체 네트워크 사용량을 주기적으로 (기본 1초) 측정합니다.
#     - 활성화된 경우 (G_ENABLE_FILE_SAVE = True), 측정된 모니터링 데이터를 주기적으로 (기본 30초) 별도의 CSV 파일 (monitoring_data_YYYYMMDD_HHMMSS.csv)에 저장합니다.
#     - 프로그램의 동작 로그를 날짜별 파일 (manager_YYYYMMDD.log)로 기록합니다.
#     - 주요 설정값 (파일 경로, argument, 시간 간격 등)은 전역 상수로 정의되어 쉽게 변경할 수 있습니다.
import subprocess
import time
import os
import psutil
import csv
from datetime import datetime
import logging

# --- 전역 상수 정의 ---
G_LOG_LEVEL = logging.INFO  # 로깅 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
G_DEFAULT_PROGRAM1_PATH_PY = "C:\\path\\to\\your\\png2jpg_Convert_v013.py"  # 프로그램 1 Python 스크립트 기본 경로
G_DEFAULT_PROGRAM1_PATH_EXE = "C:\\path\\to\\your\\png2jpg_Convert_v013.exe"  # 프로그램 1 실행 파일 기본 경로
G_DEFAULT_ARGUMENTS_LIST = [  # 프로그램 1 실행 시 사용할 기본 argument 리스트
    ["ABH125c_1"],
    ["ABH125c_2"],
    ["ABH125c_3"],
]
G_MONITORING_INTERVAL_SEC = 1  # 초 단위 모니터링 간격 (프로세스 사용량 측정)
G_FILE_SAVE_INTERVAL_SEC = 30  # 초 단위 파일 저장 간격 (모니터링 데이터 파일 저장)

# --- 전역 변수 설정 ---
G_WORKER_EXECUTE_EXE = True  # True: 프로그램 1을 Python 스크립트로 실행, False: 실행 파일로 실행
G_ENABLE_MONITORING = True  # True: 모니터링 기능 활성화, False: 비활성화
G_ENABLE_FILE_SAVE = True  # True: 파일 저장 기능 활성화, False: 비활성화
G_MONITORING_DATA = [] # 수집된 모니터링 데이터를 임시로 저장할 리스트
G_LAST_SAVE_TIME = time.time()  # 마지막으로 데이터를 파일에 저장한 시간
G_START_TIME_STR = datetime.now().strftime("%Y%m%d_%H%M%S") # 프로그램 시작 시각 (모니터링 파일명에 사용)
G_PROCESSES = {}  # 실행된 프로그램 1의 process 객체를 저장할 딕셔너리 (키: "program1_인덱스", 값: subprocess.Popen 객체)
G_PREV_DISK_IO = {}  # 각 프로그램 1 프로세스의 이전 디스크 I/O 카운터 값을 저장할 딕셔너리 (키: "program1_인덱스", 값: psutil.disk_io_counters() 객체)
G_LOG_FILE = f"manager_{datetime.now().strftime('%Y%m%d')}.log"  # 날짜별 로그 파일 이름

# --- 로깅 설정 ---
logging.basicConfig(filename=G_LOG_FILE, level=G_LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    encoding='utf-8', force=True)

# 프로그램 1의 경로 설정 (전역 변수 G_WORKER_EXECUTE_EXE 값에 따라 결정)
if G_WORKER_EXECUTE_EXE:
    PROGRAM1_PATH = G_DEFAULT_PROGRAM1_PATH_PY
else:
    PROGRAM1_PATH = G_DEFAULT_PROGRAM1_PATH_EXE

# 프로그램 1을 실행할 때 사용할 argument 리스트 (전역 상수 G_DEFAULT_ARGUMENTS_LIST 사용)
ARGUMENTS_LIST = G_DEFAULT_ARGUMENTS_LIST

def _run_program(program_path, arguments):
    # 프로그램을 실행하고 process 객체를 반환합니다.
    try:
        process = subprocess.Popen([program_path] + arguments) # subprocess.Popen을 사용하여 프로그램 실행
        logging.info(f"프로그램 실행: {program_path} {' '.join(arguments)}, PID: {process.pid}")
        return process
    except FileNotFoundError:
        logging.error(f"오류: {program_path} 파일을 찾을 수 없습니다.")
        return None
    except Exception as e:
        logging.error(f"프로그램 실행 중 오류 발생: {e}")
        return None

def get_process_usage(pid, args):
    # 주어진 PID의 프로세스의 CPU, 메모리, 디스크 IO, 네트워크 사용량을 측정합니다.
    try:
        process = psutil.Process(pid) # PID를 이용하여 psutil.Process 객체 생성
        cpu_percent = process.cpu_percent() # CPU 사용률 (%)
        memory_info = process.memory_info() # 메모리 사용 정보 객체
        rss = memory_info.rss / (1024 * 1024)  # 실제 사용 중인 물리 메모리 (Resident Set Size)를 MB 단위로 변환

        io_counters = process.io_counters() # 디스크 I/O 카운터 정보
        read_bytes = io_counters.read_bytes / (1024 * 1024)  # 읽은 바이트 수를 MB 단위로 변환
        write_bytes = io_counters.write_bytes / (1024 * 1024)  # 쓴 바이트 수를 MB 단위로 변환

        # 시스템 전체 네트워크 사용량 (프로세스별 정확한 측정은 어려움)
        net_io = psutil.net_io_counters() # 시스템 전체 네트워크 I/O 카운터
        net_sent = net_io.bytes_sent / (1024 * 1024)  # 보낸 바이트 수를 MB 단위로 변환
        net_recv = net_io.bytes_recv / (1024 * 1024)  # 받은 바이트 수를 MB 단위로 변환

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # 측정 시간
            "arguments": " ".join(args), # 프로그램 1 실행 시 사용된 argument
            "cpu_percent": cpu_percent, # CPU 사용률
            "memory_mb": rss, # 메모리 사용량 (MB)
            "disk_read_mb": read_bytes, # 디스크 읽기 (MB)
            "disk_write_mb": write_bytes, # 디스크 쓰기 (MB)
            "network_sent_mb": net_sent, # 네트워크 송신 (MB)
            "network_recv_mb": net_recv, # 네트워크 수신 (MB)
        }
    except psutil.NoSuchProcess:
        return None # 프로세스가 존재하지 않으면 None 반환
    except Exception as e:
        logging.error(f"프로세스 사용량 측정 중 오류: {e}")
        return None

def _save_monitoring_data_to_csv():
    # 모니터링 데이터를 CSV 파일에 저장합니다.
    global G_MONITORING_DATA, G_LAST_SAVE_TIME  #, G_START_TIME_STR
    if not G_MONITORING_DATA:
        return

    filename = f"monitoring_data_{datetime.now().strftime('%Y%m%d')}_{G_START_TIME_STR}.csv"
    file_exists = os.path.isfile(filename) # 파일이 이미 존재하는지 확인

    try:
        with open(filename, 'a', newline='') as csvfile: # 파일 열기 (append 모드)
            fieldnames = ["timestamp", "arguments", "cpu_percent", "memory_mb", "disk_read_mb", "disk_write_mb", "network_sent_mb", "network_recv_mb"] # CSV 헤더 필드 이름
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames) # 딕셔너리 형태의 데이터를 CSV 파일에 쓰기 위한 객체 생성

            if not file_exists:
                writer.writeheader()  # 파일이 없으면 헤더를 씁니다.

            writer.writerows(G_MONITORING_DATA)  # 데이터 리스트의 각 딕셔너리를 CSV 행으로 씁니다.

        logging.info(f"모니터링 데이터를 {filename}에 저장했습니다.")
        G_MONITORING_DATA = [] # 저장 후 데이터 리스트를 비웁니다.
        G_LAST_SAVE_TIME = time.time()  # 마지막 저장 시간 업데이트
    except Exception as e:
        logging.error(f"CSV 파일 저장 중 오류: {e}")

def check_and_restart():
    # 실행 중인 프로그램을 확인하고 중단된 경우 재실행합니다.
    global G_PROCESSES

    for i, args in enumerate(ARGUMENTS_LIST):
        process_key = f"program1_{i}"
        process_obj = G_PROCESSES.get(process_key) # 실행 중인 프로그램 1의 process 객체 가져오기

        if process_obj is None: # 아직 실행되지 않은 경우
            new_process = _run_program(PROGRAM1_PATH, args) # 프로그램 실행
            if new_process:
                G_PROCESSES[process_key] = new_process # 실행 성공 시 process 객체 저장
        elif process_obj.poll() is not None: # 프로그램이 종료된 경우 (poll()이 None이 아니면 종료됨)
            return_code = process_obj.returncode # 종료 코드 확인
            logging.info(f"프로그램 종료: {PROGRAM1_PATH} {' '.join(args)}, PID: {process_obj.pid}, 종료 코드: {return_code}")
            del G_PROCESSES[process_key] # 종료된 프로세스를 딕셔너리에서 제거
            # 재실행
            new_process = _run_program(PROGRAM1_PATH, args) # 프로그램 재실행
            if new_process:
                G_PROCESSES[process_key] = new_process # 재실행 성공 시 process 객체 저장
            else:
                logging.error(f"프로그램 재실행 실패: {PROGRAM1_PATH} {' '.join(args)}")

def _start_initial_processes():
    # 초기 프로그램 1 인스턴스들을 실행합니다.
    for i, args in enumerate(ARGUMENTS_LIST):
        process_key = f"program1_{i}"
        process = _run_program(PROGRAM1_PATH, args)
        if process:
            G_PROCESSES[process_key] = process

def _monitor_processes():
    # 실행 중인 프로그램들의 사용량을 측정하고 G_MONITORING_DATA에 저장합니다.
    global G_MONITORING_DATA

    for process_key, process_obj in G_PROCESSES.items():
        if process_obj.poll() is None and G_ENABLE_MONITORING: # 프로그램이 아직 실행 중이고 모니터링이 활성화된 경우
            process_index = int(process_key.split('_')[-1]) # process_key에서 인덱스 추출
            args = ARGUMENTS_LIST[process_index] # 해당 인덱스의 argument 가져오기
            usage_data = get_process_usage(process_obj.pid, args) # 프로세스 사용량 측정
            if usage_data:
                G_MONITORING_DATA.append(usage_data) # 측정된 데이터 리스트에 추가

if __name__ == "__main__":
    G_START_TIME_STR = datetime.now().strftime("%Y%m%d_%H%M%S") # 프로그램 시작 시각 기록
    G_LOG_FILE = f"manager_{datetime.now().strftime('%Y%m%d')}.log"  # 날짜별 로그 파일 이름 재설정
    logging.basicConfig(filename=G_LOG_FILE, level=G_LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        encoding='utf-8', force=True) # force=True for reconfiguring

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 프로그램 2 시작: 프로그램 1의 실행 상태를 {G_MONITORING_INTERVAL_SEC}초마다 확인하고 재실행합니다.")
    logging.info(f"프로그램 2 시작: 프로그램 1의 실행 상태를 {G_MONITORING_INTERVAL_SEC}초마다 확인하고 재실행합니다.")
    if G_ENABLE_MONITORING:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - CPU, 메모리, 디스크 IO 및 네트워크 사용량을 {G_MONITORING_INTERVAL_SEC}초마다 측정합니다.")
        logging.info(f"CPU, 메모리, 디스크 IO 및 네트워크 사용량을 {G_MONITORING_INTERVAL_SEC}초마다 측정합니다.")
    if G_ENABLE_FILE_SAVE:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 측정된 데이터를 {G_FILE_SAVE_INTERVAL_SEC}초마다 monitoring_data_{datetime.now().strftime('%Y%m%d')}_{G_START_TIME_STR}.csv 파일에 저장합니다.")
        logging.info(f"측정된 데이터를 {G_FILE_SAVE_INTERVAL_SEC}초마다 monitoring_data_{datetime.now().strftime('%Y%m%d')}_{G_START_TIME_STR}.csv 파일에 저장합니다.")

    _start_initial_processes() # 초기 프로그램 1 인스턴스 실행

    while True:
        _monitor_processes() # 실행 중인 프로그램들의 사용량 측정 및 저장

        check_and_restart() # 10초마다 재실행 확인 (원래 로직 유지)

        if G_ENABLE_FILE_SAVE and time.time() - G_LAST_SAVE_TIME >= G_FILE_SAVE_INTERVAL_SEC and G_MONITORING_DATA:
            _save_monitoring_data_to_csv() # 파일 저장 간격이 되면 데이터 저장

        time.sleep(G_MONITORING_INTERVAL_SEC) # 설정된 모니터링 간격으로 대기
