"""Recovery delivery: private local mailbox for demos, TLS SMTP when configured."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4


def deliver_reset(email: str, token: str):
    message = EmailMessage()
    message['Subject'] = 'Paw Protectors password recovery'
    message['From'] = os.getenv('SMTP_FROM', 'paw@localhost')
    message['To'] = email
    message.set_content(
        'A password reset was requested for your Paw Protectors account.\n'
        'Open Forgot password, then Enter recovery code in the app or website.\n'
        f'Recovery code: {token}\n'
        'This code expires in 15 minutes and works once.\n'
        'If you did not request this, ignore this message.\n'
    )
    mode = os.getenv('RECOVERY_DELIVERY', 'local')
    if mode == 'local':
        folder = Path(os.getenv('RECOVERY_MAILBOX_DIR', 'artifacts/private-mailbox'))
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f'{uuid4().hex}.eml').open('x', encoding='utf-8') as out:
            out.write(message.as_string())
    elif mode == 'smtp':
        with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT', '587')), timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
    else:
        raise RuntimeError('RECOVERY_DELIVERY must be local or smtp')
