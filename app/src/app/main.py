from pathlib import Path

from app.utils.s3_service import upload_file
from app.utils.file import file_list
from app.config import config

CURRENT_DIR = Path(__file__).parent
DATA_DIR = CURRENT_DIR / "data/fhir-sample"
# DATA_DIR = CURRENT_DIR / "data"
# FILE_PATH = DATA_DIR / "test-data.txt"
# FILE_NAME = str(FILE_PATH)

BUCKET_NAME = config.get("S3_BUCKET_NAME")
if __name__ == "__main__":
    # print("path", str(DATA_DIR))
    # print(file_list(2, DATA_DIR))

    for file in file_list(5, DATA_DIR):
        success = upload_file(file, BUCKET_NAME)
        if success:
            print(f"File {file} uploaded successfully to bucket {BUCKET_NAME}.")
        else:
            print(f"Failed to upload file {file} to bucket {BUCKET_NAME}.")

    # Temporarily disable
    # success = upload_file(FILE_NAME, BUCKET_NAME)
    # if success:
    #     print(f"File {FILE_NAME} uploaded successfully to bucket {BUCKET_NAME}.")
    # else:
    #     print(f"Failed to upload file {FILE_NAME} to bucket {BUCKET_NAME}.")
