import unittest
import os
import shutil
import time
from datetime import datetime
import configparser
from unittest.mock import patch
from multiprocessing import Queue, Manager, Process
import sys
from PIL import Image
import subprocess
import random

import png2jpg_Convert_v001
# 테스트를 위해 스크립트 import (상대 경로 주의)
# try:
#     import png2jpg_Convert_v001  # 실제 스크립트 파일 이름으로 변경
# except ImportError:
#     print("Error: 스크립트 파일을 찾을 수 없습니다. 파일 이름을 확인하세요.")
#     raise

class TestImageConverter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 전체 테스트 클래스 실행 전 한 번 실행되는 설정
        # 임시 테스트 환경을 구성합니다 (폴더 생성, 설정 파일 생성).
        cls.test_base_dir = "test_env_all"
        cls.watch_base_folder = os.path.join(cls.test_base_dir, "watch")
        cls.output_base_folder = os.path.join(cls.test_base_dir, "output")
        cls.log_folder = os.path.join(cls.test_base_dir, "log")

        cls.config_file = os.path.join("./config.ini") # 수정된 부분

        os.makedirs(cls.watch_base_folder, exist_ok=True)
        os.makedirs(cls.output_base_folder, exist_ok=True)
        os.makedirs(cls.log_folder, exist_ok=True)

        # 테스트에 사용할 config.ini 파일을 생성합니다.
        config = configparser.ConfigParser()
        config['Paths'] = {'watch_base_folder': cls.watch_base_folder,
                           'output_base_folder': cls.output_base_folder,
                           'log_folder': cls.log_folder}
        config['Image'] = {'jpg_quality': '80'}
        config['Processing'] = {'num_processes': '2'}
        with open(cls.config_file, 'w') as f:
            config.write(f)

        # 테스트 대상 스크립트가 설정 파일을 읽도록 설정
        png2jpg_Convert_v001.config_file = cls.config_file

    @classmethod
    def tearDownClass(cls):
        # 전체 테스트 클래스 실행 후 한 번 실행되는 정리
        # 임시 테스트 환경을 삭제합니다.
        shutil.rmtree(cls.test_base_dir, ignore_errors=True)

    def setUp(self):
        # 각 테스트 메서드 실행 전마다 실행되는 설정
        # 테스트에 필요한 임시 폴더 (오늘 날짜)를 생성합니다.
        self.today_str = datetime.now().strftime("%Y%m%d")
        self.watch_folder_today = os.path.join(self.watch_base_folder, self.today_str)
        os.makedirs(self.watch_folder_today, exist_ok=True)

    def tearDown(self):
        # 각 테스트 메서드 실행 후마다 실행되는 정리
        # 테스트에서 생성된 임시 폴더 및 파일을 삭제합니다.
        shutil.rmtree(self.watch_folder_today, ignore_errors=True)
        output_date_folder = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:])
        shutil.rmtree(output_date_folder, ignore_errors=True)
        log_file_today = os.path.join(self.log_folder, f"error_{self.today_str}.log")
        if os.path.exists(log_file_today):
            os.remove(log_file_today)

    def create_dummy_png(self, filename, folder=None, grayscale=True, size_mb=0.01):
        # 테스트용 더미 PNG 파일을 생성하는 helper 메서드
        if folder is None:
            folder = self.watch_folder_today
        filepath = os.path.join(folder, filename)
        mode = 'L' if grayscale else 'RGB'
        pixels = (int((size_mb * 1024 * 1024) ** 0.5) // 4) * 4
        img = Image.new(mode, (max(1, pixels // 10), max(1, pixels // 10)), color='white')
        img.save(filepath)
        return filepath

    def get_output_jpg_path(self, png_filename):
        # PNG 파일명으로부터 예상되는 출력 JPG 파일 경로를 생성하는 helper 메서드
        name, ext = os.path.splitext(png_filename)
        jpg_filename = name + ".jpg"
        output_folder = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:])
        return os.path.join(output_folder, jpg_filename)

    def run_script(self, date_arg=None):
        # 스크립트를 별도의 서브프로세스로 실행하는 helper 메서드
        script_path = os.path.abspath("./src_v001/png2jpg_Convert_v001.py")
        args = [sys.executable, script_path]
        if date_arg:
            args.append(date_arg)
        process = subprocess.Popen(args)
        return process

    def check_log_for_errors(self):
        # 오늘 날짜의 로그 파일에 에러 메시지가 없는지 확인하는 helper 메서드
        log_file = os.path.join(self.log_folder, f"error_{self.today_str}.log")
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                log_content = f.read()
                self.assertFalse(any(level in log_content for level in ["ERROR", "CRITICAL"]), f"Error found in log file: {log_content}")

    def count_files(self, folder):
        # 특정 폴더 내의 파일 개수를 세는 helper 메서드
        return len([f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))])

    @patch('time.sleep', return_value=None)
    def test_new_png_creation(self, mock_sleep):
        # 새로운 PNG 파일이 생성되면 JPG로 변환되는지 테스트합니다.
        png_filename = "test_new.png"
        self.create_dummy_png(png_filename)
        time.sleep(2)  # watchdog 이벤트 처리 대기

        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertTrue(os.path.exists(output_jpg_path))

    @patch('time.sleep', return_value=None)
    def test_modified_png_file(self, mock_sleep):
        # 기존 PNG 파일이 수정되면 JPG로 다시 변환되는지 테스트합니다.
        png_filename = "test_modified.png"
        png_path = self.create_dummy_png(png_filename)
        time.sleep(2) # 첫 번째 변환 대기

        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertTrue(os.path.exists(output_jpg_path))
        original_modified_time = os.path.getmtime(output_jpg_path)

        time.sleep(1) # 파일 수정 시간 차이 확보
        self.create_dummy_png(png_filename) # PNG 파일 수정
        time.sleep(2) # 두 번째 변환 대기

        self.assertTrue(os.path.exists(output_jpg_path))
        new_modified_time = os.path.getmtime(output_jpg_path)
        self.assertGreater(new_modified_time, original_modified_time)

    @patch('time.sleep', return_value=None)
    def test_grayscale_png(self, mock_sleep):
        # 흑백 PNG 파일이 흑백 JPG로 변환되는지 (전역 설정) 테스트합니다.
        png_filename = "test_grayscale.png"
        self.create_dummy_png(png_filename, grayscale=True)
        time.sleep(2)

        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertTrue(os.path.exists(output_jpg_path))
        # 실제 JPG 파일 열어서 흑백인지 확인하는 로직 추가 가능 (PIL 사용)

    @patch('time.sleep', return_value=None)
    def test_color_png(self, mock_sleep):
        # 컬러 PNG 파일이 컬러 JPG로 변환되는지 (전역 설정) 테스트합니다.
        png_filename = "test_color.png"
        self.create_dummy_png(png_filename, grayscale=False)
        time.sleep(2)

        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertTrue(os.path.exists(output_jpg_path))
        # 실제 JPG 파일 열어서 컬러인지 확인하는 로직 추가 가능 (PIL 사용)

    @patch('time.sleep', return_value=None)
    def test_file_stability_check(self, mock_sleep):
        # 파일이 생성되는 동안에는 변환이 일어나지 않고, 안정화된 후 변환되는지 테스트합니다.
        png_filename = "test_stable.png"
        filepath = os.path.join(self.watch_folder_today, png_filename)
        with open(filepath, 'wb') as f:
            f.write(os.urandom(1024)) # 일부 데이터 쓰기
            time.sleep(1) # 안정화 대기 시간보다 짧게 대기
            f.write(os.urandom(1024)) # 나머지 데이터 쓰기

        time.sleep(3) # watchdog 이벤트 및 안정화 확인 대기

        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertTrue(os.path.exists(output_jpg_path))

    @patch('time.sleep', return_value=None)
    def test_invalid_date_folder(self, mock_sleep):
        # 날짜 형식에 맞지 않는 폴더에는 반응하지 않는지 확인합니다 (현재는 명령행 인수로 처리).
        invalid_folder = os.path.join(self.watch_base_folder, "invalid_date")
        os.makedirs(invalid_folder, exist_ok=True)
        png_filename = "test_invalid_date.png"
        self.create_dummy_png(png_filename, folder=invalid_folder)
        time.sleep(2)

        output_jpg_path = os.path.join(self.output_base_folder, "invalid_date", png_filename.replace(".png", ".jpg"))
        self.assertFalse(os.path.exists(output_jpg_path))
        shutil.rmtree(invalid_folder, ignore_errors=True)

    @patch('time.sleep', return_value=None)
    def test_command_line_argument(self, mock_sleep):
        # 명령행 인수로 특정 날짜 폴더를 처리하는지 테스트합니다.
        specific_date = "20250320"
        watch_folder_specific = os.path.join(self.watch_base_folder, specific_date)
        os.makedirs(watch_folder_specific, exist_ok=True)
        png_filename = "test_specific_date.png"
        self.create_dummy_png(png_filename, folder=watch_folder_specific)

        # 명령행 인수를 사용하여 스크립트 실행 (별도 프로세스로 실행해야 함)
        script_path = os.path.abspath("./src_v001/png2jpg_Convert_v001.py")
        result = subprocess.run([sys.executable, script_path, specific_date], capture_output=True, text=True)
        self.assertIn(f"Processing folder for date: {specific_date}", result.stdout)

        output_jpg_path = os.path.join(self.output_base_folder, specific_date[:4], specific_date[4:6], specific_date[6:], png_filename.replace(".png", ".jpg"))
        time.sleep(2) # 처리 대기
        self.assertTrue(os.path.exists(output_jpg_path))
        shutil.rmtree(watch_folder_specific, ignore_errors=True)

    @patch('time.sleep', return_value=None)
    def test_existing_jpg_not_overwritten(self, mock_sleep):
        # 이미 JPG 파일이 존재하는 경우 덮어쓰지 않는지 (현재 로직) 테스트합니다.
        png_filename = "test_existing_jpg.png"
        output_jpg_path = self.get_output_jpg_path(png_filename)
        os.makedirs(os.path.dirname(output_jpg_path), exist_ok=True)
        with open(output_jpg_path, 'w') as f:
            f.write("existing jpg content")
        original_modified_time = os.path.getmtime(output_jpg_path)

        self.create_dummy_png(png_filename)
        time.sleep(2)

        self.assertTrue(os.path.exists(output_jpg_path))
        new_modified_time = os.path.getmtime(output_jpg_path)
        self.assertEqual(new_modified_time, original_modified_time) # 수정 시간이 그대로여야 함

    @patch('time.sleep', return_value=None)
    def test_unprocessed_files_on_startup(self, mock_sleep):
        # 스크립트 시작 시 미처리된 파일을 처리하는지 테스트합니다.
        png_filename = "test_unprocessed.png"
        self.create_dummy_png(png_filename)

        # 스크립트 실행 (별도 프로세스로)
        script_path = os.path.abspath("./src_v001/png2jpg_Convert_v001.py")
        process = subprocess.Popen([sys.executable, script_path, self.today_str])
        time.sleep(5) # 충분한 처리 시간 부여
        process.terminate()
        process.wait()

        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertTrue(os.path.exists(output_jpg_path))

    def test_concurrent_file_creation_load(self):
        # 짧은 시간 동안 여러 개의 PNG 파일이 생성될 때 스크립트가 정상적으로 처리하는지 부하 테스트합니다.
        num_files = 5  # 생성할 파일 개수
        delay = 0.5      # 파일 생성 간격 (초)

        # 스크립트 실행
        process = self.run_script(self.today_str)
        time.sleep(1) # 스크립트 시작 대기

        # 가상 파일 생성
        png_filenames = [f"test_load_{i}.png" for i in range(num_files)]
        for filename in png_filenames:
            self.create_dummy_png(filename)
            time.sleep(delay)

        time.sleep(num_files * delay + 5) # 파일 생성 시간 + 처리 예상 시간 대기
        process.terminate()
        process.join(timeout=1)

        # 결과 확인
        output_folder = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:])
        os.makedirs(output_folder, exist_ok=True) # 폴더가 없을 경우를 대비

        converted_count = self.count_files(output_folder)
        self.assertEqual(converted_count, num_files, f"Expected {num_files} JPG files, but found {converted_count}")

        self.check_log_for_errors()

    def test_concurrent_file_creation_and_modification(self):
        # 파일 생성과 동시에 일부 파일이 수정되는 상황에서 스크립트가 정상적으로 처리하는지 테스트합니다.
        num_files = 3
        delay = 1

        # 스크립트 실행
        process = self.run_script(self.today_str)
        time.sleep(1)

        png_filenames = [f"test_mod_{i}.png" for i in range(num_files)]
        for i, filename in enumerate(png_filenames):
            self.create_dummy_png(filename)
            time.sleep(delay)
            if i == 1: # 두 번째 파일 수정
                time.sleep(1)
                self.create_dummy_png(filename)
                time.sleep(delay)

        time.sleep(num_files * delay * 2 + 5) # 생성 및 수정 + 처리 시간 대기
        process.terminate()
        process.join(timeout=1)

        output_folder = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:])
        os.makedirs(output_folder, exist_ok=True)

        converted_count = self.count_files(output_folder)
        self.assertEqual(converted_count, num_files, f"Expected {num_files} JPG files (including modification), but found {converted_count}")
        self.check_log_for_errors()

    def test_no_png_files(self):
        # 감시 폴더에 PNG 파일이 없는 경우 스크립트가 에러 없이 종료되는지 확인합니다.
        process = self.run_script(self.today_str)
        time.sleep(5)
        process.terminate()
        process.join(timeout=1)
        self.check_log_for_errors()

    def test_existing_jpg_handling_load(self):
        # 이미 JPG 파일이 존재하는 경우 스크립트가 어떻게 처리하는지 테스트합니다 (현재는 덮어쓰지 않음).
        png_filename = "test_existing_load.png"
        output_jpg_path = self.get_output_jpg_path(png_filename)
        os.makedirs(os.path.dirname(output_jpg_path), exist_ok=True)
        with open(output_jpg_path, 'w') as f:
            f.write("existing jpg content")
        original_modified_time = os.path.getmtime(output_jpg_path)

        # 스크립트 실행 후 PNG 생성
        process = self.run_script(self.today_str)
        time.sleep(1)
        self.create_dummy_png(png_filename)
        time.sleep(5)
        process.terminate()
        process.join(timeout=1)

        new_modified_time = os.path.getmtime(output_jpg_path)
        self.assertEqual(new_modified_time, original_modified_time, "JPG 파일이 덮어쓰여졌습니다.")
        self.check_log_for_errors()

    def test_process_restart_after_interruption(self):
        # 프로세스가 중단된 후 재실행되었을 때 스크립트가 이전에 처리하지 못한 파일을 처리하는지 테스트합니다.
        num_files = 3

        png_filenames = [f"restart_test_{i}.png" for i in range(num_files)]
        for filename in png_filenames:
            self.create_dummy_png(filename)

        # 스크립트 실행 (첫 번째 실행)
        process1 = self.run_script(self.today_str)
        time.sleep(2) # 잠시 동안 실행되도록 대기

        # 프로세스 중단 (SIGINT 시뮬레이션)
        process1.terminate()
        process1.wait(timeout=5)

        # 스크립트 재실행
        process2 = self.run_script(self.today_str)
        time.sleep(5) # 충분히 처리할 시간 대기
        process2.terminate()
        process2.wait(timeout=5)

        # 결과 확인
        output_folder = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:])
        os.makedirs(output_folder, exist_ok=True)

        converted_count = self.count_files(output_folder)
        self.assertEqual(converted_count, num_files, f"Expected {num_files} JPG files after restart, but found {converted_count}")
        self.check_log_for_errors()

    def test_random_file_creation_and_processing(self):
        # PNG 파일이 0.2~1초 사이에 1회씩 랜덤하게 생성되고 적절한 시간에 처리되는지 확인합니다.
        num_files = 5
        min_delay = 0.2
        max_delay = 1.0
        max_wait_time = num_files * max_delay * 5 # 충분한 처리 시간 확보

        png_filenames = [f"random_test_{i}.png" for i in range(num_files)]

        # 스크립트 실행
        process = self.run_script(self.today_str)
        time.sleep(1) # 스크립트 시작 대기

        # 랜덤한 시간 간격으로 파일 생성
        for filename in png_filenames:
            delay = random.uniform(min_delay, max_delay)
            time.sleep(delay)
            self.create_dummy_png(filename)

        time.sleep(max_wait_time) # 모든 파일이 처리될 때까지 충분히 기다림
        process.terminate()
        process.join(timeout=5)

        # 결과 확인
        output_folder = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:])
        os.makedirs(output_folder, exist_ok=True)

        converted_count = self.count_files(output_folder)
        self.assertEqual(converted_count, num_files, f"Expected {num_files} JPG files, but found {converted_count}")
        self.check_log_for_errors()

    @patch('time.sleep', return_value=None)
    def test_non_png_file(self, mock_sleep):
        # 감시 폴더에 PNG 확장자가 아닌 파일이 있을 경우 스크립트가 이를 무시하는지 테스트합니다.
        txt_filename = "test_non_png.txt"
        with open(os.path.join(self.watch_folder_today, txt_filename), 'w') as f:
            f.write("This is a text file.")
        time.sleep(2)
        output_jpg_path = os.path.join(self.output_base_folder, self.today_str[:4], self.today_str[4:6], self.today_str[6:], txt_filename.replace(".txt", ".jpg"))
        self.assertFalse(os.path.exists(output_jpg_path))
        self.check_log_for_errors() # 에러 로그가 없어야 함

    @patch('time.sleep', return_value=None)
    def test_empty_png_file(self, mock_sleep):
        # 크기가 0인 빈 PNG 파일이 생성되었을 때 스크립트가 어떻게 처리하는지 테스트합니다.
        png_filename = "test_empty.png"
        open(os.path.join(self.watch_folder_today, png_filename), 'w').close()
        time.sleep(2)
        output_jpg_path = self.get_output_jpg_path(png_filename)
        self.assertFalse(os.path.exists(output_jpg_path))
        self.check_log_for_errors() # 에러 로그 확인 (경고 메시지 정도는 괜찮을 수 있음)

    @patch('time.sleep', return_value=None)
    def test_filename_with_spaces(self, mock_sleep):
        # 파일명에 공백이 포함된 PNG 파일을 스크립트가 정상적으로 처리하는지 테스트합니다.
        png_filename = "test with spaces.png"
        self.create_dummy_png(png_filename)
        time.sleep(2)
        output_jpg_path = self.get_output_jpg_path(png_filename)
        expected_output_filename = "test with spaces.jpg"
        expected_output_path = os.path.join(os.path.dirname(output_jpg_path), expected_output_filename)
        self.assertTrue(os.path.exists(expected_output_path))

    @unittest.skip("출력 폴더 권한 오류 테스트는 수동으로 환경을 설정해야 하므로 자동화된 테스트에서 제외합니다.")
    def test_output_folder_permission_error(self):
        # 스크립트가 출력 폴더에 쓰기 권한이 없는 경우 PermissionError를 제대로 처리하는지 테스트합니다.
        output_folder = os.path.join(self.test_base_dir, "no_permission_output")
        os.makedirs(output_folder)
        os.chmod(output_folder, 0o555) # 읽기 및 실행 권한만 부여

        config = configparser.ConfigParser()
        config['Paths'] = {'watch_base_folder': self.watch_base_folder,
                           'output_base_folder': output_folder,
                           'log_folder': self.log_folder}
        config['Image'] = {'jpg_quality': '80'}
        config['Processing'] = {'num_processes': '2'}
        with open(self.config_file, 'w') as f:
            config.write(f)

        png_filename = "test_permission_error.png"
        self.create_dummy_png(png_filename)
        time.sleep(3) # 에러 로깅 시간 확보

        log_file = os.path.join(self.log_folder, f"error_{self.today_str}.log")
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, 'r') as f:
            log_content = f.read()
            self.assertIn("Permission denied accessing file", log_content)

        os.chmod(output_folder, 0o777) # 권한 복구
        shutil.rmtree(output_folder, ignore_errors=True)

    def test_unreadable_png_file(self):
        # 스크립트가 유효하지 않은 PNG 파일을 만났을 때 Image.UnidentifiedImageError를 제대로 처리하는지 테스트합니다.
        png_filename = "test_unreadable.png"
        filepath = os.path.join(self.watch_folder_today, png_filename)
        with open(filepath, 'wb') as f:
            f.write(b"This is not a valid PNG file.")
        time.sleep(3) # 에러 로깅 시간 확보

        log_file = os.path.join(self.log_folder, f"error_{self.today_str}.log")
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, 'r') as f:
            log_content = f.read()
            self.assertIn("Could not open or read image file", log_content)

    def test_watch_folder_does_not_exist(self):
        # 설정 파일에 지정된 감시 폴더가 존재하지 않을 때 스크립트가 에러를 처리하고 종료하는지 테스트합니다.
        non_existent_folder = os.path.join(self.test_base_dir, "non_existent_watch")
        config = configparser.ConfigParser()
        config['Paths'] = {'watch_base_folder': non_existent_folder,
                           'output_base_folder': self.output_base_folder,
                           'log_folder': self.log_folder}
        config['Image'] = {'jpg_quality': '80'}
        config['Processing'] = {'num_processes': '2'}
        with open(self.config_file, 'w') as f:
            config.write(f)

        import subprocess
        script_path = os.path.abspath("./src_v001/png2jpg_Convert_v001.py")
        result = subprocess.run([sys.executable, script_path, self.today_str], capture_output=True, text=True)
        self.assertIn(f"Error: Watch folder does not exist: {non_existent_folder}", result.stdout)

        # 설정 복구
        config['Paths'] = {'watch_base_folder': self.watch_base_folder,
                           'output_base_folder': self.output_base_folder,
                           'log_folder': self.log_folder}
        with open(self.config_file, 'w') as f:
            config.write(f)

if __name__ == '__main__':
    import subprocess
    # 테스트 실행 전에 필요한 라이브러리 설치 확인 및 안내
    try:
        from PIL import Image
    except ImportError:
        print("Error: PIL (Pillow) 라이브러리가 설치되어 있지 않습니다. `pip install Pillow` 명령을 실행하여 설치하세요.")
        sys.exit(1)
    try:
        import watchdog
    except ImportError:
        print("Error: watchdog 라이브러리가 설치되어 있지 않습니다. `pip install watchdog` 명령을 실행하여 설치하세요.")
        sys.exit(1)

    # 실제 스크립트 파일이 있는지 확인
    script_path = os.path.abspath("./src_v001/png2jpg_Convert_v001.py")
    if not os.path.exists(script_path):
        print(f"Error: 스크립트 파일 '{script_path}'을 찾을 수 없습니다. 파일 이름을 확인하세요.")
        sys.exit(1)

    unittest.main()
