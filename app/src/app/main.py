from pathlib import Path

from app.utils.s3_service import upload_file
from app.utils.file import file_list
from app.config import config, logger

CURRENT_DIR = Path(__file__).parent
DATA_DIR = CURRENT_DIR / "data/fhir-sample"
BUCKET_NAME = config.get("S3_BUCKET_NAME")
NUM_FILES_TO_UPLOAD = 10

if __name__ == "__main__":
    logger.info(f"""Uploading {NUM_FILES_TO_UPLOAD} files
        from {DATA_DIR} to S3 bucket {BUCKET_NAME}.
        """)
    for file in file_list(NUM_FILES_TO_UPLOAD, DATA_DIR):
        success = upload_file(file, BUCKET_NAME)
        if success:
            logger.info(f"File {file} uploaded successfully to bucket {BUCKET_NAME}.")
        else:
            logger.error(f"Failed to upload file {file} to bucket {BUCKET_NAME}.")
