"""
Tests for the s3_service module.

References:
https://docs.getmoto.org/en/latest/
https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html
"""

import os
import boto3

import pytest
from moto import mock_aws

from app.utils.s3_service import upload_file


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def aws_setup(aws_credentials):
    """
    Return a mocked S3 client
    """
    with mock_aws():
        # Create a mocked S3 client and bucket
        s3_client = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-bucket"
        bucket_prefix = "raw"
        s3_client.create_bucket(Bucket=bucket_name)

        yield {
            "s3_client": s3_client,
            "bucket_name": bucket_name,
            "bucket_prefix": bucket_prefix,
        }


@pytest.fixture()
def test_file(tmp_path):
    # Create a temporary test file
    CONTENT = "Hello from S3 bucket"
    test_file_path = tmp_path / "test_file.txt"
    test_file_path.write_text(CONTENT)
    return {
        "file_path": str(test_file_path),
        "file_name": test_file_path.name,
        "content": CONTENT,
    }


class TestS3Service:
    def test_upload_file_success(self, aws_setup, test_file):
        """
        Test the upload_file function for successful upload to S3.
        """
        s3_client = aws_setup["s3_client"]
        bucket_name = aws_setup["bucket_name"]
        bucket_prefix = aws_setup["bucket_prefix"]
        file_path = test_file["file_path"]
        file_name = test_file["file_name"]
        content = test_file["content"]

        # Call the upload_file function
        result = upload_file(file_path, bucket_name)

        # Assert that the function returned True for successful upload
        assert result is True

        # Verify that file exists in bucket
        response = s3_client.get_object(
            Bucket=bucket_name, Key=f"{bucket_prefix}/{file_name}"
        )
        response_body = response["Body"].read().decode("utf-8")

        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
        assert response_body == content

    def test_upload_file_failure(self, aws_setup, test_file):
        """
        Test the upload_file function for failed upload
        to S3 due to non-existent bucket.
        """
        file_path = test_file["file_path"]

        # Call the upload_file function
        result = upload_file(
            file_path,
            "non-existent-bucket",  # Provide a non-existent bucket name
        )

        # Assert that the function returned False for failed upload
        assert result is False
