# app/utils/email_sender.py
import logging
import os
from threading import Thread
from datetime import datetime

from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail

logger = logging.getLogger(__name__)


# ── Async transport ────────────────────────────────────────────────────────────

def _send_async(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
            app.logger.info("Email sent to %s | subject='%s'", msg.recipients, msg.subject)
        except Exception:
            app.logger.error("Email delivery failed to %s | subject='%s'",
                             msg.recipients, msg.subject, exc_info=True)


# ── Core dispatcher ────────────────────────────────────────────────────────────

def send_email(subject, recipients, text_body=None, html_body=None,
               template=None, **template_ctx):
    app = current_app._get_current_object()
    msg = Message(
        subject=subject,
        sender=app.config['MAIL_DEFAULT_SENDER'],
        recipients=recipients if isinstance(recipients, list) else [recipients]
    )
    msg.body = text_body or ''
    if template:
        try:
            msg.html = render_template(template, **template_ctx)
        except Exception:
            logger.error("Template render failed for '%s'.", template, exc_info=True)
            msg.html = None
    else:
        msg.html = html_body
    Thread(target=_send_async, args=(app, msg), daemon=True).start()


# ── Registration confirmation ──────────────────────────────────────────────────

def send_registration_confirmation(user_email, user_name, event_title, event_date,
                                    event=None, user=None, registration=None):
    subject = f"🎉 Registration Confirmed – {event_title}"

    if event and user:
        app = current_app._get_current_object()

        qr_path = None
        has_qr = False
        if (registration
                and registration.qr_code
                and not registration.qr_code.startswith('data:')):
            qr_path = os.path.join(
                app.root_path, 'static', 'uploads', 'qrcodes',
                registration.qr_code
            )
            has_qr = os.path.exists(qr_path)

        msg = Message(
            subject=subject,
            sender=app.config['MAIL_DEFAULT_SENDER'],
            recipients=[user_email] if isinstance(user_email, str) else user_email
        )
        msg.body = f"Registration confirmed for {event_title}."

        try:
            msg.html = render_template(
                'emails/registration_confirmation.html',
                event=event,
                user=user,
                registration=registration,
                has_qr=has_qr,
                base_url=app.config.get('BASE_URL', 'http://localhost:5000'),
                now=datetime.utcnow(),
            )
        except Exception:
            logger.error("Template render failed for registration_confirmation.html",
                         exc_info=True)
            msg.html = None

        if has_qr:
            try:
                with open(qr_path, 'rb') as f:
                    msg.attach(
                        'qr_code.png',
                        'image/png',
                        f.read(),
                        'inline',
                        headers=[
                            ('Content-ID', '<qr_code>'),
                            ('X-Attachment-Id', 'qr_code'),
                        ]
                    )
            except Exception:
                logger.warning("QR attach failed — sending without QR", exc_info=True)

        Thread(target=_send_async, args=(app, msg), daemon=True).start()

    else:
        html_body = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
            <h2 style="color:#6366f1;">🎉 Registration Confirmed!</h2>
            <p>Dear <strong>{user_name}</strong>,</p>
            <p>Your registration for <strong>{event_title}</strong> has been confirmed.</p>
            <p><strong>Event Date:</strong> {event_date}</p>
        </div>
        """
        text_body = (
            f"Registration Confirmed!\n\nDear {user_name},\n\n"
            f"Your registration for {event_title} has been confirmed.\n"
            f"Event Date: {event_date}"
        )
        send_email(subject, user_email, text_body, html_body)


# ── Event reminder ─────────────────────────────────────────────────────────────

def send_event_reminder(user_email, user_name, event_title, event_date,
                         event=None, user=None, registration=None, base_url=None):
    subject = f"⏰ Reminder: {event_title} is tomorrow!"
    if event and user:
        send_email(
            subject=subject,
            recipients=user_email,
            template='emails/event_reminder.html',
            event=event,
            user=user,
            registration=registration,
            base_url=base_url or current_app.config.get('BASE_URL', 'http://localhost:5000'),
            now=datetime.utcnow(),
        )
    else:
        html_body = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
            <h2 style="color:#6366f1;">⏰ Event Reminder</h2>
            <p>Dear <strong>{user_name}</strong>,</p>
            <p>Reminder for <strong>{event_title}</strong> on {event_date}.</p>
            <p>Don't forget to bring your QR code ticket!</p>
        </div>
        """
        text_body = (
            f"Event Reminder\n\nDear {user_name},\n\n"
            f"Reminder: {event_title} on {event_date}.\n"
            f"Don't forget to bring your QR code ticket!"
        )
        send_email(subject, user_email, text_body, html_body)


# ── Waitlist confirmation ──────────────────────────────────────────────────────

def send_waitlist_confirmation(user_email, user_name, event_title, event_date,
                                event=None, user=None):
    subject = f"📋 You're on the Waitlist – {event_title}"
    formatted_date = (
        event_date.strftime('%A, %d %B %Y at %I:%M %p')
        if hasattr(event_date, 'strftime') else str(event_date)
    )
    html_body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;
                background:#111827;color:#e2e8f0;padding:40px;border-radius:12px;">
        <div style="background:linear-gradient(135deg,#6366f1,#a855f7,#ec4899);
                    padding:32px;border-radius:10px;text-align:center;margin-bottom:28px;">
            <p style="margin:0 0 12px;display:inline-block;background:rgba(255,255,255,0.15);
                       border:1px solid rgba(255,255,255,0.25);color:#fff;font-size:11px;
                       font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
                       padding:5px 16px;border-radius:20px;">📋&nbsp; Waitlist</p>
            <h1 style="margin:0 0 8px;color:#ffffff;font-size:26px;font-weight:700;">
                You're on the Waitlist</h1>
            <p style="margin:0;color:rgba(255,255,255,0.85);font-size:14px;">
                We'll notify you immediately if a spot opens up.</p>
        </div>
        <p style="margin:0 0 20px;color:#e2e8f0;font-size:15px;line-height:1.6;">
            Hi <strong style="color:#fff;">{user_name}</strong>,<br>
            <strong>{event_title}</strong> is currently full, but you've been added to
            the waitlist. If a confirmed participant cancels, you'll automatically be
            promoted and receive a confirmation email.</p>
        <div style="background:#1e293b;border-left:4px solid #a855f7;
                    padding:20px 24px;border-radius:8px;margin-bottom:24px;">
            <p style="margin:0 0 8px;color:#a78bfa;font-size:11px;font-weight:600;
                       letter-spacing:1.2px;text-transform:uppercase;">Event Details</p>
            <p style="margin:0 0 6px;color:#f1f5f9;font-size:16px;font-weight:700;">{event_title}</p>
            <p style="margin:0;color:#94a3b8;font-size:14px;">📅 {formatted_date}</p>
            {"<p style='margin:4px 0 0;color:#94a3b8;font-size:14px;'>📍 " + event.location + "</p>" if event else ""}
        </div>
        <div style="background:#1e293b;border-radius:10px;border:1px solid rgba(251,146,60,0.2);
                    padding:16px 20px;">
            <p style="margin:0;color:#94a3b8;font-size:13px;line-height:1.6;">
                <span style="color:#fb923c;font-weight:600;">⚠️ Note:</span>
                Waitlist spots are not guaranteed. You will only receive a confirmed
                ticket if a cancellation occurs before the event.</p>
        </div>
        <div style="margin-top:24px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);padding-top:20px;">
            <p style="margin:0;color:#475569;font-size:12px;">
                © 2026 <strong style="color:#64748b;">EventHub</strong>
                &nbsp;·&nbsp; You received this because you joined the waitlist.</p>
        </div>
    </div>
    """
    text_body = (
        f"You're on the Waitlist!\n\nDear {user_name},\n\n"
        f"{event_title} is currently full but you've been added to the waitlist.\n"
        f"Event Date: {formatted_date}\n\nWe'll notify you if a spot opens up."
    )
    send_email(subject, user_email, text_body, html_body)


# ── Cancellation confirmation ──────────────────────────────────────────────────

def send_cancellation_confirmation(user_email, user_name, event_title, event_date,
                                    event=None, user=None):
    subject = f"❌ Registration Cancelled – {event_title}"
    formatted_date = (
        event_date.strftime('%A, %d %B %Y at %I:%M %p')
        if hasattr(event_date, 'strftime') else str(event_date)
    )
    html_body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;
                background:#111827;color:#e2e8f0;padding:40px;border-radius:12px;">
        <div style="background:linear-gradient(135deg,#374151,#1f2937);
                    padding:32px;border-radius:10px;text-align:center;margin-bottom:28px;
                    border:1px solid rgba(255,255,255,0.08);">
            <p style="margin:0 0 12px;display:inline-block;background:rgba(239,68,68,0.15);
                       border:1px solid rgba(239,68,68,0.3);color:#f87171;font-size:11px;
                       font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
                       padding:5px 16px;border-radius:20px;">❌&nbsp; Cancelled</p>
            <h1 style="margin:0 0 8px;color:#ffffff;font-size:26px;font-weight:700;">
                Registration Cancelled</h1>
            <p style="margin:0;color:rgba(255,255,255,0.7);font-size:14px;">
                Your spot has been released.</p>
        </div>
        <p style="margin:0 0 20px;color:#e2e8f0;font-size:15px;line-height:1.6;">
            Hi <strong style="color:#fff;">{user_name}</strong>,<br>
            Your registration for <strong>{event_title}</strong> has been successfully
            cancelled. Your spot has been released for others.</p>
        <div style="background:#1e293b;border-left:4px solid #ef4444;
                    padding:20px 24px;border-radius:8px;margin-bottom:24px;">
            <p style="margin:0 0 8px;color:#fca5a5;font-size:11px;font-weight:600;
                       letter-spacing:1.2px;text-transform:uppercase;">Cancelled Event</p>
            <p style="margin:0 0 6px;color:#f1f5f9;font-size:16px;font-weight:700;">{event_title}</p>
            <p style="margin:0;color:#94a3b8;font-size:14px;">📅 {formatted_date}</p>
            {"<p style='margin:4px 0 0;color:#94a3b8;font-size:14px;'>📍 " + event.location + "</p>" if event else ""}
        </div>
        <div style="background:#1e293b;border-radius:10px;
                    border:1px solid rgba(99,102,241,0.2);padding:16px 20px;">
            <p style="margin:0;color:#94a3b8;font-size:13px;line-height:1.6;">
                <span style="color:#818cf8;font-weight:600;">💡 Changed your mind?</span>
                You can re-register for this event if seats are still available.
                <a href="http://127.0.0.1:5000/participant/events"
                   style="color:#a855f7;text-decoration:underline;font-weight:500;">
                    Browse Events</a></p>
        </div>
        <div style="margin-top:24px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);padding-top:20px;">
            <p style="margin:0;color:#475569;font-size:12px;">
                © 2026 <strong style="color:#64748b;">EventHub</strong>
                &nbsp;·&nbsp; You received this because you cancelled a registration.</p>
        </div>
    </div>
    """
    text_body = (
        f"Registration Cancelled\n\nDear {user_name},\n\n"
        f"Your registration for {event_title} has been cancelled.\n"
        f"Event Date: {formatted_date}\n\n"
        f"Your spot has been released. You can re-register if seats are available."
    )
    send_email(subject, user_email, text_body, html_body)


# ── Waitlist promotion ─────────────────────────────────────────────────────────

def send_waitlist_promotion(user_email, user_name, event_title, event_date,
                             event=None, user=None, registration=None):
    subject = f"🎉 You're In! Waitlist Confirmed – {event_title}"
    formatted_date = (
        event_date.strftime('%A, %d %B %Y at %I:%M %p')
        if hasattr(event_date, 'strftime') else str(event_date)
    )
    html_body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;
                background:#111827;color:#e2e8f0;padding:40px;border-radius:12px;">
        <div style="background:linear-gradient(135deg,#059669,#10b981);
                    padding:32px;border-radius:10px;text-align:center;margin-bottom:28px;">
            <p style="margin:0 0 12px;display:inline-block;background:rgba(255,255,255,0.15);
                       border:1px solid rgba(255,255,255,0.25);color:#fff;font-size:11px;
                       font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
                       padding:5px 16px;border-radius:20px;">🎉&nbsp; Confirmed</p>
            <h1 style="margin:0 0 8px;color:#ffffff;font-size:26px;font-weight:700;">
                You're In!</h1>
            <p style="margin:0;color:rgba(255,255,255,0.85);font-size:14px;">
                A spot opened up — your waitlist registration is now confirmed.</p>
        </div>
        <p style="margin:0 0 20px;color:#e2e8f0;font-size:15px;line-height:1.6;">
            Hi <strong style="color:#fff;">{user_name}</strong>,<br>
            Great news! A confirmed participant cancelled and you've been
            <strong style="color:#10b981;">promoted from the waitlist</strong>
            to a confirmed registration for:</p>
        <div style="background:#1e293b;border-left:4px solid #10b981;
                    padding:20px 24px;border-radius:8px;margin-bottom:24px;">
            <p style="margin:0 0 8px;color:#6ee7b7;font-size:11px;font-weight:600;
                       letter-spacing:1.2px;text-transform:uppercase;">Your Event</p>
            <p style="margin:0 0 6px;color:#f1f5f9;font-size:16px;font-weight:700;">{event_title}</p>
            <p style="margin:0;color:#94a3b8;font-size:14px;">📅 {formatted_date}</p>
            {"<p style='margin:4px 0 0;color:#94a3b8;font-size:14px;'>📍 " + event.location + "</p>" if event else ""}
        </div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
               style="margin-bottom:24px;">
            <tr>
                <td align="center">
                    <a href="http://127.0.0.1:5000/participant/registrations"
                       style="display:inline-block;background:linear-gradient(135deg,#059669,#10b981);
                               color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;
                               padding:14px 36px;border-radius:10px;letter-spacing:0.3px;">
                        🎫&nbsp; View My Ticket</a>
                </td>
            </tr>
        </table>
        <div style="margin-top:24px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);padding-top:20px;">
            <p style="margin:0;color:#475569;font-size:12px;">
                © 2026 <strong style="color:#64748b;">EventHub</strong>
                &nbsp;·&nbsp; You received this because you were on the waitlist.</p>
        </div>
    </div>
    """
    text_body = (
        f"Great news, {user_name}!\n\n"
        f"You've been promoted from the waitlist for {event_title}.\n"
        f"Event Date: {formatted_date}\n\nPlease log in to view your ticket."
    )
    send_email(subject, user_email, text_body, html_body)


# ── Event status change ────────────────────────────────────────────────────────

def send_event_status_change(user_email, user_name, event_title, new_status,
                              reason=None, postponed_to=None):
    status_labels = {
        'cancelled': ('❌ Event Cancelled', '#ef4444'),
        'postponed': ('📅 Event Postponed', '#fb923c'),
    }
    label, color = status_labels.get(new_status, ('Event Updated', '#6366f1'))
    subject = f"{label} – {event_title}"

    postponed_row = ""
    if new_status == 'postponed' and postponed_to:
        postponed_row = (
            f"<p><strong>New Date:</strong> "
            f"{postponed_to.strftime('%A, %d %B %Y at %I:%M %p') if hasattr(postponed_to, 'strftime') else postponed_to}"
            f"</p>"
        )

    html_body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;
                background:#111827;color:#e2e8f0;padding:40px;border-radius:12px;">
        <h2 style="color:{color};">{label}</h2>
        <p>Dear <strong>{user_name}</strong>,</p>
        <p>We regret to inform you that <strong>{event_title}</strong>
           has been <strong>{new_status}</strong>.</p>
        {"<p><strong>Reason:</strong> " + reason + "</p>" if reason else ""}
        {postponed_row}
        <p>We apologise for any inconvenience caused.</p>
        <p style="margin-top:24px;color:#475569;font-size:12px;
                   border-top:1px solid rgba(255,255,255,0.06);padding-top:16px;">
            © 2026 EventHub</p>
    </div>
    """
    text_body = (
        f"{label}\n\nDear {user_name},\n\n"
        f"{event_title} has been {new_status}.\n"
        + (f"Reason: {reason}\n" if reason else "")
        + (f"New Date: {postponed_to}\n" if postponed_to else "")
        + "\nWe apologise for any inconvenience."
    )
    send_email(subject, user_email, text_body, html_body)
