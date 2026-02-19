import qrcode
import io
import base64
from flask import current_app


class QRService:
    """QR code generation and validation"""
    
    @staticmethod
    def generate_ticket_qr(registration_id):
        """Generate QR code for event ticket"""
        try:
            # QR data format
            qr_data = f"REG-{registration_id}"
            
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            current_app.logger.info(f"QR code generated for registration: {registration_id}")
            return f"data:image/png;base64,{img_str}"
            
        except Exception as e:
            current_app.logger.error(f"QR generation failed: {str(e)}")
            return None
    
    @staticmethod
    def decode_qr(qr_data):
        """Decode QR data to get registration ID"""
        try:
            if qr_data.startswith("REG-"):
                reg_id = int(qr_data.replace("REG-", ""))
                return reg_id
            return None
        except:
            return None
