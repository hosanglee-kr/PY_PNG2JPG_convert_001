import subprocess
import time
import os

# 프로그램 1의 경로 (실제 경로로 수정해야 함)
program1_path = "C:\\path\\to\\your\\png2jpg_Convert_v013.py"

# 프로그램 1을 실행할 때 사용할 각기 다른 argument
arguments_list = [
    ["ABH125c_1"],
    ["ABH125c_2"],
    ["ABH125c_3"],
]

# 실행된 프로그램 1의 process를 저장할 딕셔너리
processes = {}

def run_program(program_path, arguments):
    """프로그램을 실행하고 process 객체를 반환합니다."""
    try:
        process = subprocess.Popen([program_path] + arguments)
        print(f"프로그램 실행: {program_path} {' '.join(arguments)}, PID: {process.pid}")
        return process
    except FileNotFoundError:
        print(f"오류: {program_path} 파일을 찾을 수 없습니다.")
        return None
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {e}")
        return None

def check_and_restart():
    """실행 중인 프로그램을 확인하고 중단된 경우 재실행합니다."""
    global processes
    for i, args in enumerate(arguments_list):
        process_key = f"program1_{i}"
        process = processes.get(process_key)

        if process is None:
            # 아직 실행되지 않은 경우
            new_process = run_program(program1_path, args)
            if new_process:
                processes[process_key] = new_process
        else:
            # 실행 중인 경우 상태 확인
            if process.poll() is not None:
                # 프로그램이 종료됨
                return_code = process.returncode
                print(f"프로그램 종료: {program1_path} {' '.join(args)}, PID: {process.pid}, 종료 코드: {return_code}")
                # 재실행
                new_process = run_program(program1_path, args)
                if new_process:
                    processes[process_key] = new_process
                else:
                    # 재실행 실패 시 기존 process 제거
                    del processes[process_key]

if __name__ == "__main__":
    print("프로그램 2 시작: 프로그램 1의 실행 상태를 10초마다 확인하고 재실행합니다.")

    # 초기 실행
    for i, args in enumerate(arguments_list):
        process_key = f"program1_{i}"
        process = run_program(program1_path, args)
        if process:
            processes[process_key] = process

    while True:
        check_and_restart()
        time.sleep(10)
