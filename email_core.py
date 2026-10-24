"""Delivery of a clearly labelled POC draft contract summary."""

import base64
import os
import re
import smtplib
import ssl
from email.message import EmailMessage

import requests

from contract_core import contract_pdf


# One plain mailbox: list separators, brackets and quotes would let a header name extra recipients.
EMAIL_PATTERN = re.compile(r'^[^\s@,;:<>()\[\]"\\]+@[^\s@,;:<>()\[\]"\\]+\.[^\s@,;:<>()\[\]"\\]+$')
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")  # RFC 2606


class DeliveryError(ValueError):
    pass


def _recipients(primary_email, copy_email):
    requested = [primary_email] + ([copy_email] if copy_email else [])
    if any(not isinstance(address, str) or not EMAIL_PATTERN.fullmatch(address.strip()) for address in requested):
        raise DeliveryError("Enter a valid primary and optional copy email address")
    recipients_by_key = {}
    for address in requested:
        recipients_by_key.setdefault(address.strip().lower(), address.strip())
    recipients = list(recipients_by_key.values())
    domains = [address.rsplit("@", 1)[1].lower() for address in recipients]
    if any(domain == reserved or domain.endswith("." + reserved) for domain in domains for reserved in RESERVED_DOMAINS):
        raise DeliveryError("Replace the fictional example.com address before sending")
    return recipients


def _message(record, sender, recipients):
    order_id = record["productOrder"]["id"]
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipients[0]
    if len(recipients) > 1:
        message["Cc"] = recipients[1]
    message["Subject"] = f"Draft contract summary for POC order {order_id}"
    message.set_content("Attached is a draft POC contract summary. It is not a binding contract or a service activation. Commercial and regulatory disclosures are still incomplete.")
    message.add_attachment(contract_pdf(record), maintype="application", subtype="pdf",
                           filename=f"draft-contract-{order_id}.pdf")
    return message


def _send_gmail(record, recipients, access_token):
    if not os.environ.get("GMAIL_OAUTH_CLIENT_ID"):
        raise DeliveryError("Gmail sending is not configured for this project")
    if not isinstance(access_token, str) or not access_token:
        raise DeliveryError("Connect your Google mailbox before sending")
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        profile = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers, timeout=15)
        if profile.status_code in (401, 403):
            raise DeliveryError("Google sign-in expired. Connect your mailbox again")
        profile.raise_for_status()
        sender = profile.json().get("email", "")
        if not EMAIL_PATTERN.fullmatch(sender) or profile.json().get("email_verified") is not True:
            raise DeliveryError("Google did not verify the sender mailbox")
        expected = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
        if expected and sender.lower() != expected.lower():
            raise DeliveryError(f"Connect {expected} to send this draft contract")
        raw = base64.urlsafe_b64encode(_message(record, sender, recipients).as_bytes()).decode("ascii")
        response = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                                 headers={**headers, "Content-Type": "application/json"},
                                 json={"raw": raw}, timeout=30)
        if response.status_code == 401:
            raise DeliveryError("Google sign-in expired. Connect your mailbox again")
        if response.status_code == 403:
            error = response.json().get("error", {})
            reason = " ".join([str(error.get("status", "")), str(error.get("message", ""))]).lower()
            if "scope" in reason or "permission" in reason:
                raise DeliveryError("Gmail send permission was not granted. Try again and tick ‘Send email on your behalf’ in Google's consent window")
            raise DeliveryError("Gmail rejected the send request. Check that the sender mailbox is enabled and the Gmail API is available")
        response.raise_for_status()
        message_id = response.json().get("id")
        if not message_id:
            raise DeliveryError("Gmail did not confirm delivery")
        return {"recipients": recipients, "sender": sender, "provider": "gmail", "messageId": message_id}
    except requests.RequestException as exc:
        raise DeliveryError("Gmail delivery failed. Please try again") from exc


def send_contract(record, primary_email, copy_email=None, gmail_access_token=None):
    recipients = _recipients(primary_email, copy_email)
    if os.environ.get("MAIL_PROVIDER", "smtp").lower() == "gmail":
        return _send_gmail(record, recipients, gmail_access_token)
    host, sender = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_FROM")
    username, password = os.environ.get("SMTP_USERNAME"), os.environ.get("SMTP_PASSWORD")
    if not host or not sender or bool(username) != bool(password):
        raise DeliveryError("SMTP delivery is not configured; download the PDF instead")
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise DeliveryError("SMTP port is invalid") from exc
    message = _message(record, sender, recipients)
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if username:
                smtp.login(username, password)
            smtp.send_message(message, to_addrs=recipients)
    except (OSError, smtplib.SMTPException) as exc:
        raise DeliveryError("Email delivery failed; check the SMTP connection and credentials") from exc
    return {"recipients": recipients, "sender": sender, "provider": "smtp", "messageId": None}
