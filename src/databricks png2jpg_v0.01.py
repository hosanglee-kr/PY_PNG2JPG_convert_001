from pyspark.sql import SparkSession
from PIL import Image
import io
import os
from pyspark.sql.functions import col, lit

# Gen2 계정 정보 설정 (Databricks 환경 설정에 따라 다를 수 있음)
# 예시: 액세스 키 방식 (권장하지 않음)
# spark.conf.set("fs.azure.account.key.<your_adlsg2_account_name>.dfs.core.windows.net", "<your_adlsg2_access_key>")

# 예시: Azure Active Directory (AAD) passthrough (권장) - 클러스터 설정 필요
# 예시: 서비스 주체 인증 - 클러스터 설정 필요

def convert_png_to_jpg(partition):
    """
    PNG 이미지를 JPG로 변환하고 Gen2에 저장하는 함수 (파티션 단위 처리).

    Args:
        partition (iterator): 파일 경로와 내용의 튜플을 포함하는 iterator.
    """
    output_adls_path = "abfss://<output_container_name>@<your_adlsg2_account_name>.dfs.core.windows.net/<output_jpg_path>/"  # 출력 Gen2 경로 설정

    for file_path, content in partition:
        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_file_path = f"{output_adls_path}{base_name}.jpg"

            image = Image.open(io.BytesIO(content))
            if image.mode == 'RGBA':
                image = image.convert('RGB')

            # Databricks File System (DBFS)를 통해 Gen2에 저장
            dbfs_output_path = f"/dbfs{output_file_path.replace('abfss://', '/')}"
            image.save(dbfs_output_path, "JPEG")
            print(f"Successfully converted and saved to Gen2: {file_path} -> {output_file_path}")
        except Exception as e:
            print(f"Error converting {file_path}: {e}")

if __name__ == "__main__":
    spark = SparkSession.builder.appName("PngToJpgConverter").getOrCreate()
    sc = spark.sparkContext

    # 입력 Gen2 경로 설정
    input_adls_path = "abfss://<input_container_name>@<your_adlsg2_account_name>.dfs.core.windows.net/<input_png_path>/"

    # Pillow 라이브러리 배포 (Databricks 클러스터에 설치되어 있어야 함)
    # sc.addPyFile("/path/to/Pillow-x.x.x-py3-none-any.whl") # 필요한 경우 Pillow 휠 파일 추가

    try:
        # 입력 Gen2 경로의 모든 PNG 파일 읽기 (파일 경로와 내용)
        png_files_rdd = sc.binaryFiles(input_adls_path + "*.png")  # 특정 패턴으로 필터링 가능

        # 각 파티션별로 이미지 변환 함수 적용
        png_files_rdd.foreachPartition(convert_png_to_jpg)

        print("PNG to JPG 변환 및 Gen2 저장 완료.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        spark.stop()