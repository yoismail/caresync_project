"""
Notification module for sending alerts via Slack and Email.

"""
import logging
import smtplib
from email.mime.text import MIMEText
import requests
from python.config import SLACK_WEBHOOK_URL, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL
from python.logger import setup_logging


def send_alert(subject, message):
    full_msg = subject + "\n\n" + message
    logging.info(full_msg)

    # Send Slack
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={
                          "text": full_msg}, timeout=10)
            logging.info("Slack alert sent")
        except Exception as e:
            logging.error("Slack failed: " + str(e))

    # Send Email
    if all([SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL]):
        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = SMTP_USER
            msg["To"] = NOTIFICATION_EMAIL
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            logging.info("Email alert sent")
        except Exception as e:
            logging.error("Email failed: " + str(e))


def main():

    setup_logging()
    send_alert("Test Alert", "This is a test alert message.")


if __name__ == "__main__":
    main()
