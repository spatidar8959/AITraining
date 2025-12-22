"""
Alert Service for Circuit Breaker and System Notifications
Sends email alerts and logs critical events
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

from app.config import settings

# Setup logger
logger = logging.getLogger(__name__)


class AlertService:
    """Email and logging alert service"""

    def __init__(self):
        """Initialize alert service"""
        self.email_enabled = settings.ALERT_EMAIL_ENABLED
        self.email_to = settings.ALERT_EMAIL_TO
        self.email_from = settings.ALERT_EMAIL_FROM
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS

    def send_circuit_breaker_alert(
        self,
        job_id: int,
        video_id: int,
        consecutive_failures: int,
        threshold: int
    ) -> bool:
        """
        Send circuit breaker alert when threshold is reached.

        Args:
            job_id: Training job ID
            video_id: Video ID
            consecutive_failures: Number of consecutive failures
            threshold: Circuit breaker threshold

        Returns:
            True if alert sent successfully (or email disabled)
        """
        subject = f"🚨 Circuit Breaker Triggered - Training Job #{job_id}"

        message_body = f"""
        <html>
        <body>
            <h2>Circuit Breaker Triggered</h2>
            <p><strong>Training job has been paused due to consecutive failures.</strong></p>

            <table style="border-collapse: collapse; width: 100%;">
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Job ID:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{job_id}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Video ID:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{video_id}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Consecutive Failures:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{consecutive_failures}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Threshold:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{threshold}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Timestamp:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{datetime.utcnow().isoformat()}</td>
                </tr>
            </table>

            <h3>Action Required:</h3>
            <ul>
                <li>Check system logs for detailed error messages</li>
                <li>Verify Qdrant service is running</li>
                <li>Verify Google Vertex AI credentials and quotas</li>
                <li>Review failed frames in database</li>
                <li>Resume job manually after resolving issues</li>
            </ul>

            <p><em>This is an automated alert from the Asset Training System.</em></p>
        </body>
        </html>
        """

        # Log alert (always log)
        logger.critical(
            f"CIRCUIT BREAKER TRIGGERED: Job #{job_id}, Video #{video_id}, "
            f"{consecutive_failures} consecutive failures (threshold: {threshold})"
        )

        # Send email if enabled
        if self.email_enabled:
            return self._send_email(subject, message_body)
        else:
            logger.info("Email alerts disabled, skipping email notification")
            return True

    def send_training_failure_alert(
        self,
        job_id: int,
        video_id: int,
        error_message: str
    ) -> bool:
        """
        Send alert when training job fails completely.

        Args:
            job_id: Training job ID
            video_id: Video ID
            error_message: Error description

        Returns:
            True if alert sent successfully
        """
        subject = f"❌ Training Job Failed - Job #{job_id}"

        message_body = f"""
        <html>
        <body>
            <h2>Training Job Failed</h2>
            <p><strong>A training job has failed and requires attention.</strong></p>

            <table style="border-collapse: collapse; width: 100%;">
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Job ID:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{job_id}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Video ID:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{video_id}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Error:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;"><pre>{error_message}</pre></td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Timestamp:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{datetime.utcnow().isoformat()}</td>
                </tr>
            </table>

            <p><em>This is an automated alert from the Asset Training System.</em></p>
        </body>
        </html>
        """

        # Log alert
        logger.error(f"TRAINING JOB FAILED: Job #{job_id}, Video #{video_id}, Error: {error_message}")

        # Send email if enabled
        if self.email_enabled:
            return self._send_email(subject, message_body)
        else:
            return True

    def _send_email(self, subject: str, html_body: str) -> bool:
        """
        Send HTML email via SMTP.

        Args:
            subject: Email subject
            html_body: HTML email body

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not configured, cannot send email")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            msg['Subject'] = subject

            # Attach HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            # Connect to SMTP server
            if self.smtp_use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)

            # Login and send
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.email_from, [self.email_to], msg.as_string())
            server.quit()

            logger.info(f"Email alert sent successfully to {self.email_to}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}", exc_info=True)
            return False


# Singleton instance
alert_service = AlertService()
