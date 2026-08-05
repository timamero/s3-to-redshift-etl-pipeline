from pathlib import Path

from app.utils.s3_service import upload_file
from app.utils.file import file_list
from app.config import config

CURRENT_DIR = Path(__file__).parent
DATA_DIR = CURRENT_DIR / "data/fhir-sample"
BUCKET_NAME = config.get("S3_BUCKET_NAME")

if __name__ == "__main__":

    for file in file_list(5, DATA_DIR):
        success = upload_file(file, BUCKET_NAME)
        if success:
            print(f"File {file} uploaded successfully to bucket {BUCKET_NAME}.")
        else:
            print(f"Failed to upload file {file} to bucket {BUCKET_NAME}.")
