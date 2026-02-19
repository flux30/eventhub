"""
Email utility — covers every notification scenario:

  1.  Registration confirmation  + ticket PDF attachment
  2.  Waitlist added
  3.  Waitlist promoted → confirmed  + ticket PDF
  4.  Registration cancelled (participant self-cancel)
  5.  Event cancelled by organizer  (blast to all registrants)
  6.  Event updated  (date/location changed)
  7.  Payment verified
  8.  Event reminder  (called by scheduler, 24h before)
  9.  Feedback request  (after event ends)
  10. Welcome email  (on account registration)
  11. Password reset OTP

All sends are wrapped in try/except — a failed email
never crashes the main request.
"""

import os
import io
from datetime import datetime
from flask import current_app
from flask_mail import Message
from app.extensions import mail


# ─────────────────────────────────────────────────────────────────────────────
# PDF ticket generator
# ─────────────────────────────────────────────────────────────────────────────

def _generate_ticket_pdf(user, event, registration):
    """
    Build an in-memory PDF ticket using ReportLab.
    Returns bytes ready to attach to an email.
    Falls back to None if ReportLab is not installed.
    """
    try:
        from reportlab.lib.pagesizes import A5
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas

        buf   = io.BytesIO()
        w, h  = A5          # 148 × 210 mm
        c     = rl_canvas.Canvas(buf, pagesize=A5)

        # ── Background ────────────────────────────────────────────────────────
        c.setFillColorRGB(0.07, 0.09, 0.13)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # ── Header bar ────────────────────────────────────────────────────────
        c.setFillColorRGB(0.3, 0.65, 1.0)
        c.rect(0, h - 28*mm, w, 28*mm, fill=1, stroke=0)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(w / 2, h - 18*mm, "EventHub")
        c.setFont("Helvetica", 10)
        c.drawCentredString(w / 2, h - 25*mm, "OFFICIAL TICKET")

        # ── Event title ───────────────────────────────────────────────────────
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 14)
        # Wrap long titles
        title = event.title if len(event.title) <= 42 else event.title[:39] + "..."
        c.drawCentredString(w / 2, h - 40*mm, title)

        # ── Divider ───────────────────────────────────────────────────────────
        c.setStrokeColorRGB(0.3, 0.65, 1.0)
        c.setLineWidth(1)
        c.line(15*mm, h - 44*mm, w - 15*mm, h - 44*mm)

        # ── Detail rows ───────────────────────────────────────────────────────
        c.setFillColorRGB(0.65, 0.75, 0.85)
        c.setFont("Helvetica", 9)

        rows = [
            ("Attendee",   user.name),
            ("Date",       event.event_date.strftime("%A, %d %B %Y")),
            ("Time",       event.event_date.strftime("%I:%M %p")),
            ("Location",   event.location[:48] if event.location else "—"),
            ("Ticket #",   f"#{registration.id:06d}"),
            ("Status",     registration.status.upper()),
        ]
        if event.is_paid:
            rows.append(("Amount", f"Rs. {float(event.price):.2f}"))

        y = h - 52*mm
        for label, value in rows:
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(0.5, 0.6, 0.7)
            c.drawString(15*mm, y, label)
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(colors.white)
            c.drawString(55*mm, y, value)
            y -= 8*mm

        # ── QR placeholder block ──────────────────────────────────────────────
        # Embed actual QR PNG if it exists on disk
        qr_path = None
        if registration.qr_code:
            qr_path = os.path.join(
                current_app.root_path,
                'static', 'uploads', 'qrcodes',
                registration.qr_code
            )

        qr_y = 18*mm
        qr_size = 28*mm

        if qr_path and os.path.exists(qr_path):
            c.drawImage(
                qr_path,
                w / 2 - qr_size / 2, qr_y,
                width=qr_size, height=qr_size,
                preserveAspectRatio=True
            )
        else:
            # Fallback: grey placeholder box
            c.setFillColorRGB(0.15, 0.18, 0.23)
            c.rect(w / 2 - qr_size / 2, qr_y, qr_size, qr_size, fill=1, stroke=0)
            c.setFillColorRGB(0.5, 0.6, 0.7)
            c.setFont("Helvetica", 7)
            c.drawCentredString(w / 2, qr_y + qr_size / 2, "QR Code")

        # ── Footer ────────────────────────────────────────────────────────────
        c.setFillColorRGB(0.35, 0.45, 0.55)
        c.setFont("Helvetica", 7)
        c.drawCentredString(w / 2, 10*mm, "Present this ticket at the venue entrance.")
        c.drawCentredString(w / 2,  6*mm, f"Generated {datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC")

        c.save()
        buf.seek(0)
        return buf.read()

    except ImportError:
        current_app.logger.warning("[Email] ReportLab not installed — ticket PDF skipped")
        return None
    except Exception as e:
        current_app.logger.warning(f"[Email] PDF generation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Internal send helper
# ─────────────────────────────────────────────────────────────────────────────

def _send(msg):
    """Send a Flask-Mail Message object. Logs on failure, never raises."""
    try:
        mail.send(msg)
        current_app.logger.info(f"[Email] Sent '{msg.subject}' → {msg.recipients}")
    except Exception as e:
        current_app.logger.warning(f"[Email] Failed to send '{msg.subject}': {e}")


def _base_url():
    return current_app.config.get('BASE_URL', 'http://127.0.0.1:5000')


def _sender():
    return current_app.config.get('MAIL_DEFAULT_SENDER', 'EventHub <noreply@eventhub.com>')


# ─────────────────────────────────────────────────────────────────────────────
# 1. Registration Confirmation  +  Ticket PDF
# ─────────────────────────────────────────────────────────────────────────────

def send_registration_confirmation(user, event, registration):
    ticket_url = f"{_base_url()}/participant/ticket/{registration.id}"

    msg         = Message(
        subject    = f"✅ You're registered: {event.title}",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#3b82f6;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">You're registered! 🎉</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Your spot for <strong>{event.title}</strong> is confirmed.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 0;color:#9ca3af;width:40%">📅 Date</td><td><strong>{event.event_date.strftime('%A, %d %B %Y')}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">⏰ Time</td><td><strong>{event.event_date.strftime('%I:%M %p')}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">📍 Location</td><td><strong>{event.location}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">🎫 Ticket #</td><td><strong>#{registration.id:06d}</strong></td></tr>
          {"<tr><td style='padding:8px 0;color:#9ca3af;'>💳 Payment</td><td><strong style='color:#f59e0b;'>Pending</strong></td></tr>" if event.is_paid else ""}
        </table>
        <a href="{ticket_url}"
           style="display:inline-block;background:#3b82f6;color:#fff;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;margin:8px 0;">
          View Ticket &amp; QR Code →
        </a>
        <p style="margin-top:24px;color:#6b7280;font-size:13px;">
          Your ticket PDF is attached to this email. Show it at the venue entrance.
        </p>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub · You received this because you registered for an event.
      </div>
    </div>
    """

    # Attach PDF ticket
    pdf = _generate_ticket_pdf(user, event, registration)
    if pdf:
        msg.attach(
            filename    = f"ticket_{registration.id:06d}.pdf",
            content_type= "application/pdf",
            data        = pdf
        )

    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Added to Waitlist
# ─────────────────────────────────────────────────────────────────────────────

def send_waitlist_confirmation(user, event):
    msg = Message(
        subject    = f"⏳ You're on the waitlist: {event.title}",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#f59e0b;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">You're on the waitlist ⏳</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p><strong>{event.title}</strong> is currently full, but you've been added to the waitlist.</p>
        <p>We'll notify you immediately if a spot opens up. No action needed from you.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 0;color:#9ca3af;width:40%">📅 Date</td><td><strong>{event.event_date.strftime('%A, %d %B %Y')}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">📍 Location</td><td><strong>{event.location}</strong></td></tr>
        </table>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub · You'll be notified if a spot becomes available.
      </div>
    </div>
    """
    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Waitlist Promoted → Confirmed  +  Ticket PDF
# ─────────────────────────────────────────────────────────────────────────────

def send_waitlist_promotion_email(user, event, registration):
    ticket_url = f"{_base_url()}/participant/ticket/{registration.id}"

    msg = Message(
        subject    = f"🎟️ Great news! Your spot is confirmed: {event.title}",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#10b981;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">Spot confirmed! 🎉</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>A spot just opened and you've been <strong>moved from the waitlist to confirmed</strong> for <strong>{event.title}</strong>!</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 0;color:#9ca3af;width:40%">📅 Date</td><td><strong>{event.event_date.strftime('%A, %d %B %Y')}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">⏰ Time</td><td><strong>{event.event_date.strftime('%I:%M %p')}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">📍 Location</td><td><strong>{event.location}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">🎫 Ticket #</td><td><strong>#{registration.id:06d}</strong></td></tr>
        </table>
        <a href="{ticket_url}"
           style="display:inline-block;background:#10b981;color:#fff;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;">
          View My Ticket →
        </a>
        <p style="margin-top:24px;color:#6b7280;font-size:13px;">Your ticket PDF is attached.</p>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub
      </div>
    </div>
    """

    pdf = _generate_ticket_pdf(user, event, registration)
    if pdf:
        msg.attach(
            filename     = f"ticket_{registration.id:06d}.pdf",
            content_type = "application/pdf",
            data         = pdf
        )

    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Registration Cancelled (by participant)
# ─────────────────────────────────────────────────────────────────────────────

def send_cancellation_confirmation(user, event):
    msg = Message(
        subject    = f"❌ Registration cancelled: {event.title}",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#ef4444;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">Registration Cancelled</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Your registration for <strong>{event.title}</strong> on
           <strong>{event.event_date.strftime('%d %B %Y')}</strong> has been cancelled.</p>
        <p>If this was a mistake, you can re-register at
           <a href="{_base_url()}/participant/events/{event.id}" style="color:#3b82f6;">the event page</a>
           (subject to availability).
        </p>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub
      </div>
    </div>
    """
    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Event Cancelled by Organizer (blast to all registrants)
# ─────────────────────────────────────────────────────────────────────────────

def send_event_cancellation_blast(event, reason=''):
    """
    Call this from the organizer route when an event is cancelled.
    Pass the full list of Registration objects (or User objects).
    """
    from app.models import Registration
    registrations = Registration.query.filter_by(
        event_id=event.id, status='confirmed'
    ).all()

    for reg in registrations:
        try:
            msg = Message(
                subject    = f"⚠️ Event Cancelled: {event.title}",
                sender     = _sender(),
                recipients = [reg.user.email]
            )
            msg.html = f"""
            <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
              <div style="background:#dc2626;padding:28px 32px;">
                <h1 style="margin:0;font-size:22px;color:#fff;">Event Cancelled ⚠️</h1>
              </div>
              <div style="padding:32px;">
                <p>Hi <strong>{reg.user.name}</strong>,</p>
                <p>We're sorry to inform you that <strong>{event.title}</strong> scheduled for
                   <strong>{event.event_date.strftime('%d %B %Y')}</strong> has been cancelled.</p>
                {"<p><strong>Reason:</strong> " + reason + "</p>" if reason else ""}
                <p style="color:#9ca3af;">If you made a payment, please contact the organiser for a refund.</p>
              </div>
              <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
                EventHub
              </div>
            </div>
            """
            _send(msg)
        except Exception as e:
            current_app.logger.warning(f"[Email] Blast to {reg.user.email} failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Event Updated (date / location changed)
# ─────────────────────────────────────────────────────────────────────────────

def send_event_update_notification(event, changes: dict):
    """
    changes = {'Date': ('12 Mar', '15 Mar'), 'Location': ('Hall A', 'Hall B')}
    """
    from app.models import Registration
    registrations = Registration.query.filter_by(
        event_id=event.id, status='confirmed'
    ).all()

    changes_html = "".join(
        f"<tr><td style='padding:6px 0;color:#9ca3af;'>{k}</td>"
        f"<td><s style='color:#6b7280'>{old}</s> → <strong style='color:#10b981'>{new}</strong></td></tr>"
        for k, (old, new) in changes.items()
    )

    for reg in registrations:
        try:
            msg = Message(
                subject    = f"📝 Event Updated: {event.title}",
                sender     = _sender(),
                recipients = [reg.user.email]
            )
            msg.html = f"""
            <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
              <div style="background:#7c3aed;padding:28px 32px;">
                <h1 style="margin:0;font-size:22px;color:#fff;">Event Updated 📝</h1>
              </div>
              <div style="padding:32px;">
                <p>Hi <strong>{reg.user.name}</strong>,</p>
                <p>Details for <strong>{event.title}</strong> have changed:</p>
                <table style="width:100%;border-collapse:collapse;margin:16px 0;">{changes_html}</table>
                <a href="{_base_url()}/participant/events/{event.id}"
                   style="display:inline-block;background:#7c3aed;color:#fff;padding:12px 28px;
                          border-radius:8px;text-decoration:none;font-weight:bold;">
                  View Updated Event →
                </a>
              </div>
              <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
                EventHub
              </div>
            </div>
            """
            _send(msg)
        except Exception as e:
            current_app.logger.warning(f"[Email] Update notify to {reg.user.email} failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Payment Verified
# ─────────────────────────────────────────────────────────────────────────────

def send_payment_confirmation(user, event, registration):
    ticket_url = f"{_base_url()}/participant/ticket/{registration.id}"
    msg = Message(
        subject    = f"💳 Payment confirmed: {event.title}",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#10b981;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">Payment Confirmed 💳</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Your payment of <strong>Rs. {float(event.price):.2f}</strong> for
           <strong>{event.title}</strong> has been verified.</p>
        <a href="{ticket_url}"
           style="display:inline-block;background:#10b981;color:#fff;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;">
          Download Ticket →
        </a>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub
      </div>
    </div>
    """
    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Event Reminder  (call 24 hours before via scheduler / cron)
# ─────────────────────────────────────────────────────────────────────────────

def send_event_reminder(user, event, registration):
    ticket_url = f"{_base_url()}/participant/ticket/{registration.id}"
    msg = Message(
        subject    = f"⏰ Reminder: {event.title} is tomorrow!",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#f59e0b;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">See you tomorrow! ⏰</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Just a reminder that <strong>{event.title}</strong> is happening <strong>tomorrow</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 0;color:#9ca3af;width:40%">⏰ Time</td><td><strong>{event.event_date.strftime('%I:%M %p')}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">📍 Location</td><td><strong>{event.location}</strong></td></tr>
          <tr><td style="padding:8px 0;color:#9ca3af;">🎫 Ticket #</td><td><strong>#{registration.id:06d}</strong></td></tr>
        </table>
        <a href="{ticket_url}"
           style="display:inline-block;background:#f59e0b;color:#111;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;">
          View My Ticket →
        </a>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub
      </div>
    </div>
    """
    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Feedback Request  (after event ends)
# ─────────────────────────────────────────────────────────────────────────────

def send_feedback_request(user, event):
    event_url = f"{_base_url()}/participant/events/{event.id}"
    msg = Message(
        subject    = f"💬 How was {event.title}? Share your feedback",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#3b82f6;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">How was the event? 💬</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Thank you for attending <strong>{event.title}</strong>! We'd love to hear your thoughts.</p>
        <a href="{event_url}#feedback"
           style="display:inline-block;background:#3b82f6;color:#fff;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;">
          Leave Feedback →
        </a>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub · Takes less than 60 seconds.
      </div>
    </div>
    """
    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Welcome Email  (on new account registration)
# ─────────────────────────────────────────────────────────────────────────────

def send_welcome_email(user):
    msg = Message(
        subject    = "👋 Welcome to EventHub!",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#3b82f6;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">Welcome to EventHub 🎉</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Your account has been created successfully. Here's what you can do:</p>
        <ul style="color:#9ca3af;line-height:2;">
          <li>Browse and register for events</li>
          <li>Get QR-code tickets instantly</li>
          <li>Track your registrations and history</li>
        </ul>
        <a href="{_base_url()}/participant/events"
           style="display:inline-block;background:#3b82f6;color:#fff;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;margin-top:8px;">
          Browse Events →
        </a>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub
      </div>
    </div>
    """
    _send(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Password Reset OTP
# ─────────────────────────────────────────────────────────────────────────────

def send_password_reset_email(user, reset_url):
    msg = Message(
        subject    = "🔐 Reset your EventHub password",
        sender     = _sender(),
        recipients = [user.email]
    )
    msg.html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;background:#111827;color:#e5e7eb;border-radius:12px;overflow:hidden;">
      <div style="background:#ef4444;padding:28px 32px;">
        <h1 style="margin:0;font-size:22px;color:#fff;">Password Reset 🔐</h1>
      </div>
      <div style="padding:32px;">
        <p>Hi <strong>{user.name}</strong>,</p>
        <p>Click below to reset your password. This link expires in <strong>30 minutes</strong>.</p>
        <a href="{reset_url}"
           style="display:inline-block;background:#ef4444;color:#fff;padding:14px 32px;
                  border-radius:8px;text-decoration:none;font-weight:bold;">
          Reset Password →
        </a>
        <p style="margin-top:24px;color:#6b7280;font-size:13px;">
          If you didn't request this, you can safely ignore this email.
        </p>
      </div>
      <div style="background:#1f2937;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
        EventHub
      </div>
    </div>
    """
    _send(msg)
