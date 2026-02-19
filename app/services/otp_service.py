import random
from datetime import datetime, timedelta
from flask import current_app
from app.extensions import mail
from flask_mail import Message


class OTPService:
    """Handle OTP generation, storage, and verification"""
    
    # In-memory OTP storage (use Redis in production)
    _otp_store = {}
    
    @staticmethod
    def generate_otp(length=4):
        """Generate random 4-digit OTP"""
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
    
    @staticmethod
    def send_otp(email, purpose='verification'):
        """
        Send OTP to email
        Purpose: 'verification' or 'password_reset'
        """
        try:
            # Generate OTP
            otp = OTPService.generate_otp()
            
            # Store OTP with expiry (5 minutes)
            key = f"{email}:{purpose}"
            OTPService._otp_store[key] = {
                'otp': otp,
                'expires_at': datetime.utcnow() + timedelta(minutes=5),
                'attempts': 0
            }
            
            # Prepare email
            subject = 'EventHub - Email Verification' if purpose == 'verification' else 'EventHub - Password Reset'
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; padding: 20px; margin: 0; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: #1e293b; padding: 40px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }}
                    .header {{ text-align: center; margin-bottom: 30px; }}
                    .header h1 {{ color: #6366f1; font-size: 32px; margin: 0 0 10px 0; }}
                    .header p {{ color: #94a3b8; font-size: 16px; margin: 0; }}
                    .content {{ color: #e2e8f0; line-height: 1.6; }}
                    .otp-box {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); padding: 24px; text-align: center; font-size: 48px; font-weight: bold; letter-spacing: 16px; border-radius: 12px; margin: 30px 0; color: white; font-family: 'Courier New', monospace; }}
                    .info-box {{ background: #334155; padding: 16px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #6366f1; }}
                    .info-box p {{ margin: 0; color: #cbd5e1; font-size: 14px; }}
                    .footer {{ text-align: center; color: #64748b; font-size: 13px; margin-top: 40px; padding-top: 20px; border-top: 1px solid #334155; }}
                    .warning {{ color: #fbbf24; font-weight: 600; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎫 EventHub</h1>
                        <p>{'Verify your email address' if purpose == 'verification' else 'Reset your password'}</p>
                    </div>
                    
                    <div class="content">
                        <p>Hello,</p>
                        <p>Your verification code is:</p>
                        
                        <div class="otp-box">{otp}</div>
                        
                        <div class="info-box">
                            <p><span class="warning">⏰ Valid for 5 minutes</span> - Please enter this code to complete your {'registration' if purpose == 'verification' else 'password reset'}.</p>
                        </div>
                        
                        <p>If you didn't request this code, please ignore this email or contact support if you have concerns.</p>
                    </div>
                    
                    <div class="footer">
                        <p>&copy; 2026 EventHub. All rights reserved.</p>
                        <p>Secure Event Management Platform</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Send email
            msg = Message(
                subject=subject,
                recipients=[email],
                html=html_body
            )
            
            mail.send(msg)
            
            current_app.logger.info(f"✅ OTP sent to {email} for {purpose}: {otp}")  # Remove in production
            return True, "OTP sent successfully"
            
        except Exception as e:
            current_app.logger.error(f"❌ Failed to send OTP: {e}")
            return False, str(e)
    
    @staticmethod
    def verify_otp(email, otp, purpose='verification'):
        """Verify OTP"""
        key = f"{email}:{purpose}"
        
        if key not in OTPService._otp_store:
            return False, "OTP not found or expired"
        
        stored_data = OTPService._otp_store[key]
        
        # Check expiry
        if datetime.utcnow() > stored_data['expires_at']:
            del OTPService._otp_store[key]
            return False, "OTP expired. Please request a new one."
        
        # Check attempts
        if stored_data['attempts'] >= 3:
            del OTPService._otp_store[key]
            return False, "Too many incorrect attempts. Please request a new OTP."
        
        # Verify OTP
        if stored_data['otp'] == otp:
            del OTPService._otp_store[key]
            return True, "OTP verified successfully"
        else:
            stored_data['attempts'] += 1
            remaining = 3 - stored_data['attempts']
            return False, f"Invalid OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
    
    @staticmethod
    def resend_otp(email, purpose='verification'):
        """Resend OTP"""
        key = f"{email}:{purpose}"
        
        # Delete old OTP if exists
        if key in OTPService._otp_store:
            del OTPService._otp_store[key]
        
        # Send new OTP
        return OTPService.send_otp(email, purpose)
