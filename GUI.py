import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QTextEdit, 
                               QGroupBox, QScrollArea, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage
from PIL import Image
import qrcode
import socketio
import uuid
import base64
import io
import os
from datetime import datetime

class SocketIOThread(QThread):
    """Thread to handle Socket.IO connection"""
    connected = Signal()
    disconnected = Signal()
    photo_received = Signal(dict)
    connection_error = Signal(str)
    
    def __init__(self, session_id):
        super().__init__()
        self.session_id = session_id
        self.sio = socketio.Client()
        self.should_run = True
        self.setup_handlers()
        
    def setup_handlers(self):
        @self.sio.on('connect')
        def on_connect():
            self.connected.emit()
            self.sio.emit('register_desktop', {'session_id': self.session_id})
            
        @self.sio.on('disconnect')
        def on_disconnect():
            self.disconnected.emit()
            
        @self.sio.on('photo_received')
        def on_photo(data):
            self.photo_received.emit(data)
            
    def run(self):
        try:
            # Replace with your actual Socket.IO server URL
            # For production: deploy server to Render, Railway, Heroku, etc.
            self.sio.connect('https://web-img.onrender.com')
        except Exception as e:
            self.connection_error.emit(str(e))
            
    def disconnect(self):
        self.should_run = False
        if self.sio.connected:
            self.sio.disconnect()

class PhotoReceiverApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Generate unique session ID
        self.session_id = str(uuid.uuid4())
        
        # File validation settings
        self.MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        self.ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/jpg', 'image/webp'}
        
        # Create save directory
        self.save_dir = "received_photos"
        os.makedirs(self.save_dir, exist_ok=True)
        
        # Setup UI
        self.init_ui()
        
        # Start Socket.IO connection in thread
        self.socket_thread = SocketIOThread(self.session_id)
        self.socket_thread.connected.connect(self.on_connected)
        self.socket_thread.disconnected.connect(self.on_disconnected)
        self.socket_thread.photo_received.connect(self.handle_photo)
        self.socket_thread.connection_error.connect(self.on_connection_error)
        self.socket_thread.start()
        
    def init_ui(self):
        self.setWindowTitle("QR Photo Receiver")
        self.setMinimumSize(900, 700)
        
        # Apply modern styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #333;
            }
            QLabel {
                color: #333;
            }
            QTextEdit {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: black;
                padding: 8px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }
            QPushButton {
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #5568d3;
            }
            QPushButton:pressed {
                background-color: #4451b8;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("📸 QR Photo Receiver")
        title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
            padding: 10px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        subtitle = QLabel("Scan QR code with your phone camera to send photos")
        subtitle.setStyleSheet("font-size: 13px; color: #666; padding-bottom: 10px;")
        subtitle.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle)
        
        # Top section - QR and Info side by side
        top_layout = QHBoxLayout()
        
        # QR Code section
        qr_group = QGroupBox("QR Code")
        qr_layout = QVBoxLayout()
        qr_layout.setAlignment(Qt.AlignCenter)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setStyleSheet("""
            background-color: white;
            padding: 15px;
            border-radius: 8px;
        """)
        self.generate_qr_code()
        qr_layout.addWidget(self.qr_label)
        
        qr_group.setLayout(qr_layout)
        top_layout.addWidget(qr_group, 1)
        
        # Info section
        info_group = QGroupBox("Connection Info")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(15)
        
        # Session ID
        session_container = QVBoxLayout()
        session_title = QLabel("Session ID:")
        session_title.setStyleSheet("font-weight: normal; font-size: 12px; color: #666;")
        self.session_label = QLabel(f"{self.session_id[:20]}...")
        self.session_label.setStyleSheet("""
            font-family: 'Courier New', monospace;
            font-size: 11px;
            background-color: #f0f0f0;
            padding: 8px;
            border-radius: 4px;
        """)
        self.session_label.setWordWrap(True)
        session_container.addWidget(session_title)
        session_container.addWidget(self.session_label)
        info_layout.addLayout(session_container)
        
        # Status
        status_container = QVBoxLayout()
        status_title = QLabel("Status:")
        status_title.setStyleSheet("font-weight: normal; font-size: 12px; color: #666;")
        self.status_label = QLabel("⏳ Connecting...")
        self.status_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #ff9800;
            background-color: #fff3e0;
            padding: 8px;
            border-radius: 4px;
        """)
        status_container.addWidget(status_title)
        status_container.addWidget(self.status_label)
        info_layout.addLayout(status_container)
        
        # Save location
        save_container = QVBoxLayout()
        save_title = QLabel("Save Location:")
        save_title.setStyleSheet("font-weight: normal; font-size: 12px; color: #666;")
        save_path = QLabel(os.path.abspath(self.save_dir))
        save_path.setStyleSheet("""
            font-size: 10px;
            color: #666;
            background-color: #f0f0f0;
            padding: 8px;
            border-radius: 4px;
        """)
        save_path.setWordWrap(True)
        save_container.addWidget(save_title)
        save_container.addWidget(save_path)
        info_layout.addLayout(save_container)
        
        info_layout.addStretch()
        info_group.setLayout(info_layout)
        top_layout.addWidget(info_group, 1)
        
        main_layout.addLayout(top_layout)
        
        # Activity Log
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # Preview section
        preview_group = QGroupBox("Last Received Photo")
        preview_layout = QVBoxLayout()
        preview_layout.setAlignment(Qt.AlignCenter)
        
        self.preview_label = QLabel("No photos received yet")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            color: #999;
            font-size: 13px;
            padding: 30px;
        """)
        self.preview_label.setMinimumHeight(250)
        preview_layout.addWidget(self.preview_label)
        
        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)
        
        self.log_message("Application started. Waiting for connection...")
        
    def generate_qr_code(self):
        """Generate QR code with session URL"""
        # URL that phone will open - replace with your actual server URL
        # For production, deploy to Render, Heroku, Railway, etc.
        server_url = f"https://web-img.onrender.com/upload?session={self.session_id}"
        
        # For local testing with ngrok:
        # server_url = f"http://your-ngrok-url.ngrok.io/upload?session={self.session_id}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(server_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((280, 280))
        img.show()
        
        # Convert PIL image to QPixmap
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        qimage = QImage.fromData(img_byte_arr.getvalue())
        pixmap = QPixmap.fromImage(qimage)
        self.qr_label.setPixmap(pixmap)
        
    def on_connected(self):
        """Handle successful connection"""
        self.status_label.setText("✅ Connected")
        self.status_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #4caf50;
            background-color: #e8f5e9;
            padding: 8px;
            border-radius: 4px;
        """)
        self.log_message("✅ Connected to server successfully")
        
    def on_disconnected(self):
        """Handle disconnection"""
        self.status_label.setText("❌ Disconnected")
        self.status_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #f44336;
            background-color: #ffebee;
            padding: 8px;
            border-radius: 4px;
        """)
        self.log_message("❌ Disconnected from server")
        
    def on_connection_error(self, error):
        """Handle connection error"""
        self.status_label.setText("❌ Connection Failed")
        self.status_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #f44336;
            background-color: #ffebee;
            padding: 8px;
            border-radius: 4px;
        """)
        self.log_message(f"❌ Connection error: {error}")
        
    def validate_photo(self, file_data, mime_type, file_size):
        """Validate file type and size"""
        if mime_type not in self.ALLOWED_TYPES:
            return False, f"Invalid file type: {mime_type}. Allowed: JPEG, PNG, WebP"
            
        if file_size > self.MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            max_mb = self.MAX_FILE_SIZE / (1024 * 1024)
            return False, f"File too large: {size_mb:.1f}MB (max: {max_mb}MB)"
            
        return True, "Valid"
        
    def handle_photo(self, data):
        """Handle received photo"""
        try:
            # Extract photo data
            photo_base64 = data.get('photo')
            mime_type = data.get('mime_type', 'image/jpeg')
            file_size = data.get('file_size', 0)
            
            # Validate
            is_valid, message = self.validate_photo(photo_base64, mime_type, file_size)
            if not is_valid:
                self.log_message(f"❌ Validation failed: {message}")
                return
                
            # Decode base64
            photo_data = base64.b64decode(photo_base64)
            
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = mime_type.split('/')[-1]
            filename = f"photo_{timestamp}.{ext}"
            filepath = os.path.join(self.save_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(photo_data)
                
            size_kb = file_size / 1024
            self.log_message(f"✅ Photo received: {filename} ({size_kb:.1f} KB)")
            
            # Update preview
            self.update_preview(photo_data)
            
        except Exception as e:
            self.log_message(f"❌ Error processing photo: {str(e)}")
            
    def update_preview(self, photo_data):
        """Update photo preview"""
        try:
            img = Image.open(io.BytesIO(photo_data))
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize for preview (maintain aspect ratio)
            img.thumbnail((400, 300), Image.Resampling.LANCZOS)
            
            # Convert to QPixmap
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            qimage = QImage.fromData(img_byte_arr.getvalue())
            pixmap = QPixmap.fromImage(qimage)
            
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setStyleSheet("")
            
        except Exception as e:
            self.log_message(f"❌ Error updating preview: {str(e)}")
            
    def log_message(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_text.append(log_entry)
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def closeEvent(self, event):
        """Handle window close"""
        self.log_message("Shutting down...")
        if hasattr(self, 'socket_thread'):
            self.socket_thread.disconnect()
            self.socket_thread.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern look
    window = PhotoReceiverApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()