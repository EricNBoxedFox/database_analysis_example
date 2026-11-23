
# functions/email_alert.py

import smtplib
import ssl
import mimetypes

from pathlib import Path
from html import escape

from email.message import EmailMessage
from email.policy import SMTP
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from typing import Optional

from functions.pgp_handler import encrypt_and_sign

# ============================================================
# Had AI modify my old code here from my NAS for reporting to
# add cc and bcc contacts, and cleanup the structure and add 
# comments. As well as clean up emails.
# ============================================================

def _normalize_recipients(recipients) -> list[str]:
    """Normalize email recipient lists."""

    if recipients is None:
        return []

    if isinstance(recipients, str):
        recipients = [recipients]

    if not isinstance(recipients, (list, tuple)):
        raise TypeError("Recipients must be a string or list")

    result = []

    for recipient in recipients:

        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("Invalid recipient address")

        result.append(recipient.strip())

    return list(dict.fromkeys(result))


def _build_email_content(
    sender: str,
    subject: str,
    header: str,
    body: str,
    footer: str,
    to: list[str],
    cc: list[str],
    body_is_html: bool = False,
    attachments: Optional[list[str]] = None
) -> EmailMessage:
    """Build the original email before encryption."""

    message = EmailMessage()

    message["From"] = sender
    message["Subject"] = subject

    if to:
        message["To"] = ", ".join(to)

    if cc:
        message["Cc"] = ", ".join(cc)

    plain_body = "\n\n".join(
        part for part in [header, body, footer] if part
    )

    message.set_content(plain_body)

    if body_is_html:

        body_html = body or ""

    else:

        body_html = escape(body or "").replace(
            "\n", "<br>\n"
        )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">

        <h2>{escape(header or "")}</h2>

        <div style="line-height: 1.6;">
            {body_html}
        </div>

        <hr>

        <footer style="font-size: 12px; color: #777;">
            {escape(footer or "")}
        </footer>

    </body>
    </html>
    """

    message.add_alternative(html_content, subtype="html")

    # Attach files to the inner message.
    if attachments:

        for attachment in attachments:

            file_path = Path(attachment)

            if not file_path.is_file():
                raise FileNotFoundError(
                    f"Attachment not found: {file_path}"
                )

            content_type, encoding = mimetypes.guess_type(
                str(file_path)
            )

            if content_type is None or encoding is not None:
                content_type = "application/octet-stream"

            maintype, subtype = content_type.split("/", 1)

            with file_path.open("rb") as file:

                message.add_attachment(
                    file.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=file_path.name
                )

    return message


def _build_pgp_mime(
    encrypted_data: bytes,
    sender: str,
    to: list[str],
    cc: list[str],
    encrypted_subject: str
):
    """Build an RFC 3156 PGP/MIME encrypted message."""

    outer = MIMEMultipart(
        "encrypted",
        protocol="application/pgp-encrypted"
    )

    outer["From"] = sender
    outer["Subject"] = encrypted_subject

    if to:
        outer["To"] = ", ".join(to)

    if cc:
        outer["Cc"] = ", ".join(cc)

    # PGP/MIME control part.
    control = MIMEBase(
        "application",
        "pgp-encrypted"
    )

    control.set_payload("Version: 1")
    encoders.encode_7or8bit(control)

    outer.attach(control)

    # ASCII-armored encrypted data.
    encrypted_part = MIMEBase(
        "application",
        "octet-stream"
    )

    encrypted_part.set_payload(
        encrypted_data.decode("ascii")
    )

    encoders.encode_7or8bit(encrypted_part)

    encrypted_part.add_header(
        "Content-Disposition",
        "inline",
        filename="encrypted.asc"
    )

    outer.attach(encrypted_part)

    return outer


def send_email(
    smtp_host: str,
    smtp_port: int,
    email_address: str,
    email_password: Optional[str],

    smtp_auth: bool = True,

    subject: str = "Automated Notification",
    header: str = "",
    body: str = "",
    footer: str = "",

    from_email: Optional[str] = None,

    to=None,
    cc=None,
    bcc=None,

    use_ssl: bool = False,
    start_tls: bool = True,

    body_is_html: bool = False,

    attachments: Optional[list[str]] = None,

    timeout: int = 30,

    # PGP CONFIGURATION
    pgp_enabled: bool = False,
    pgp_sign: bool = True,
    pgp_encrypt: bool = True,

    pgp_recipient_keys: Optional[list[str]] = None,

    pgp_private_key_path: Optional[str] = None,
    pgp_private_key_password: Optional[str] = None,

    encrypted_subject: str = "Encrypted Notification",

    extra_headers: Optional[dict[str, str]] = None
) -> bool:
    """
    Send ordinary or PGP-encrypted SMTP emails.

    PGP encryption protects the complete inner MIME message,
    including attachments.

    BCC addresses are never included in visible email headers.

    Returns:
        True when SMTP accepts the message.
    """

    # --------------------------------------------------------
    # VALIDATE SMTP CONFIGURATION
    # --------------------------------------------------------

    if not smtp_host:
        raise ValueError("SMTP host is required")

    if not isinstance(smtp_port, int) or not 1 <= smtp_port <= 65535:
        raise ValueError("Invalid SMTP port")

    if smtp_auth and (not email_address or not email_password):
        raise ValueError("SMTP credentials are required")

    if use_ssl and start_tls:
        raise ValueError("SSL and STARTTLS cannot both be enabled")

    if not use_ssl and not start_tls:
        raise ValueError("An encrypted SMTP connection is required")

    sender = from_email or email_address

    if not sender:
        raise ValueError("Sender address is required")

    # --------------------------------------------------------
    # NORMALIZE RECIPIENTS
    # --------------------------------------------------------

    to_recipients = _normalize_recipients(to)
    cc_recipients = _normalize_recipients(cc)
    bcc_recipients = _normalize_recipients(bcc)

    all_recipients = list(dict.fromkeys(
        to_recipients + cc_recipients + bcc_recipients
    ))

    if not all_recipients:
        raise ValueError("At least one recipient is required")

    # --------------------------------------------------------
    # VALIDATE PGP CONFIGURATION
    # --------------------------------------------------------

    if pgp_enabled:

        if not pgp_encrypt:
            raise ValueError(
                "This PGP/MIME implementation requires encryption."
            )

        if not pgp_recipient_keys:
            raise ValueError("Recipient public keys are required")

        if pgp_sign:

            if not pgp_private_key_path:
                raise ValueError("Application private key is required")

            if pgp_private_key_password is None:
                raise ValueError("Private key password is required (may be empty string)")

    # --------------------------------------------------------
    # BUILD ORIGINAL EMAIL
    # --------------------------------------------------------

    message = _build_email_content(
        sender=sender,
        subject=subject,
        header=header,
        body=body,
        footer=footer,
        to=to_recipients,
        cc=cc_recipients,
        body_is_html=body_is_html,
        attachments=attachments
    )

    # --------------------------------------------------------
    # PGP ENCRYPTION AND SIGNING
    # --------------------------------------------------------

    if pgp_enabled:

        original_data = message.as_bytes(policy=SMTP)

        encrypted_data = encrypt_and_sign(
            data=original_data,

            recipient_public_keys=pgp_recipient_keys,

            recipient_ids=all_recipients,

            private_key_path=pgp_private_key_path,

            private_key_password=pgp_private_key_password,

            sign=pgp_sign
        )

        message = _build_pgp_mime(
            encrypted_data=encrypted_data,

            sender=sender,

            to=to_recipients,

            cc=cc_recipients,

            encrypted_subject=encrypted_subject
        )

    # --------------------------------------------------------
    # APPLY EXTRA HEADERS
    # --------------------------------------------------------
    if extra_headers:
        for header_name, header_value in extra_headers.items():
            try:
                message[header_name] = header_value
            except Exception:
                pass

    # --------------------------------------------------------
    # SMTP CONNECTION
    # --------------------------------------------------------

    context = ssl.create_default_context()

    if use_ssl:

        smtp_connection = smtplib.SMTP_SSL(
            smtp_host,
            smtp_port,
            context=context,
            timeout=timeout
        )

    else:

        smtp_connection = smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=timeout
        )

    with smtp_connection as smtp:

        smtp.ehlo()

        if start_tls:
            smtp.starttls(context=context)
            smtp.ehlo()

        if smtp_auth:
            smtp.login(email_address, email_password)

        smtp.send_message(
            message,
            from_addr=sender,
            to_addrs=all_recipients
        )

    return True
