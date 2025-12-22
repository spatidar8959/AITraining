"""
AWS S3 Service for file upload, download, and management
"""
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional, BinaryIO
from pathlib import Path
import os

from app.config import settings
from app.utils.logger import app_logger


class S3Service:
    """Service class for AWS S3 operations"""

    def __init__(self):
        """Initialize S3 client with AWS credentials"""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            self.bucket_name = settings.S3_BUCKET_NAME
            app_logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
        except NoCredentialsError:
            app_logger.error("AWS credentials not found")
            raise
        except Exception as e:
            app_logger.error(f"Failed to initialize S3 client: {str(e)}")
            raise

    def upload_file(
        self,
        file_path: str,
        s3_key: str,
        content_type: Optional[str] = None
    ) -> bool:
        """
        Upload a file to S3.

        Args:
            file_path: Local file path to upload
            s3_key: S3 object key (path in bucket)
            content_type: MIME type of file (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args if extra_args else None
            )
            app_logger.info(f"File uploaded to S3: {s3_key}")
            return True

        except FileNotFoundError:
            app_logger.error(f"File not found: {file_path}")
            return False
        except ClientError as e:
            app_logger.error(f"S3 upload error: {str(e)}")
            return False
        except Exception as e:
            app_logger.error(f"Unexpected error during S3 upload: {str(e)}")
            return False

    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        s3_key: str,
        content_type: Optional[str] = None
    ) -> bool:
        """
        Upload a file object to S3.

        Args:
            file_obj: File-like object to upload
            s3_key: S3 object key (path in bucket)
            content_type: MIME type of file (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            file_obj.seek(0)  # Reset file pointer
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args if extra_args else None
            )
            app_logger.info(f"File object uploaded to S3: {s3_key}")
            return True

        except ClientError as e:
            app_logger.error(f"S3 upload error: {str(e)}")
            return False
        except Exception as e:
            app_logger.error(f"Unexpected error during S3 upload: {str(e)}")
            return False

    def download_file(self, s3_key: str, local_path: str) -> bool:
        """
        Download a file from S3.

        Args:
            s3_key: S3 object key (path in bucket)
            local_path: Local destination path

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            self.s3_client.download_file(
                self.bucket_name,
                s3_key,
                local_path
            )
            app_logger.info(f"File downloaded from S3: {s3_key} -> {local_path}")
            return True

        except ClientError as e:
            app_logger.error(f"S3 download error: {str(e)}")
            return False
        except Exception as e:
            app_logger.error(f"Unexpected error during S3 download: {str(e)}")
            return False

    def download_file_to_memory(self, s3_key: str) -> Optional[bytes]:
        """
        Download a file from S3 directly to memory (no local storage).

        Args:
            s3_key: S3 object key (path in bucket)

        Returns:
            File bytes if successful, None otherwise
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            file_bytes = response['Body'].read()
            app_logger.debug(f"File downloaded to memory from S3: {s3_key} ({len(file_bytes)} bytes)")
            return file_bytes

        except ClientError as e:
            app_logger.error(f"S3 download to memory error: {str(e)}")
            return None
        except Exception as e:
            app_logger.error(f"Unexpected error during S3 download to memory: {str(e)}")
            return None

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3.

        Args:
            s3_key: S3 object key (path in bucket)

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            app_logger.info(f"File deleted from S3: {s3_key}")
            return True

        except ClientError as e:
            app_logger.error(f"S3 delete error: {str(e)}")
            return False
        except Exception as e:
            app_logger.error(f"Unexpected error during S3 delete: {str(e)}")
            return False

    def delete_files_batch(self, s3_keys: list[str]) -> bool:
        """
        Delete multiple files from S3 in a batch.

        Args:
            s3_keys: List of S3 object keys to delete

        Returns:
            True if successful, False otherwise
        """
        if not s3_keys:
            return True

        try:
            objects = [{'Key': key} for key in s3_keys]
            self.s3_client.delete_objects(
                Bucket=self.bucket_name,
                Delete={'Objects': objects}
            )
            app_logger.info(f"Batch deleted {len(s3_keys)} files from S3")
            return True

        except ClientError as e:
            app_logger.error(f"S3 batch delete error: {str(e)}")
            return False
        except Exception as e:
            app_logger.error(f"Unexpected error during S3 batch delete: {str(e)}")
            return False

    def generate_presigned_url(
        self,
        s3_key: str,
        expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate a presigned URL for temporary file access.

        Args:
            s3_key: S3 object key (path in bucket)
            expiration: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL string, or None if failed
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return url

        except ClientError as e:
            app_logger.error(f"Failed to generate presigned URL: {str(e)}")
            return None
        except Exception as e:
            app_logger.error(f"Unexpected error generating presigned URL: {str(e)}")
            return None

    def file_exists(self, s3_key: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            s3_key: S3 object key (path in bucket)

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                app_logger.error(f"Error checking file existence: {str(e)}")
                return False
        except Exception as e:
            app_logger.error(f"Unexpected error checking file existence: {str(e)}")
            return False

    def get_file_size(self, s3_key: str) -> Optional[int]:
        """
        Get file size in bytes.

        Args:
            s3_key: S3 object key (path in bucket)

        Returns:
            File size in bytes, or None if failed
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return response['ContentLength']

        except ClientError as e:
            app_logger.error(f"Error getting file size: {str(e)}")
            return None
        except Exception as e:
            app_logger.error(f"Unexpected error getting file size: {str(e)}")
            return None


# Create singleton instance
s3_service = S3Service()
