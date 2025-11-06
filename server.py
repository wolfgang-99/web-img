from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import os
import logging
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size

CORS(app, resources={r"/*": {"origins": "*"}})
# socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=True, engineio_logger=True) # for high concurrency/traffic
socketio = SocketIO( app, cors_allowed_origins="*", logger=True, engineio_logger=True, 
                    max_http_buffer_size=15 * 1024 * 1024,  # 15MB max payload size
                    ping_timeout=60,ping_interval=25
                    )

# Store active sessions: {session_id: desktop_sid}
active_sessions = {}

@app.route('/')
def index():
    """Server status page"""
    return render_template("index.html")

@app.route('/upload')
def upload_page():
    """Mobile upload page"""
    session_id = request.args.get('session', '')
    if not session_id:
        return """
        <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h2>❌ Invalid Session</h2>
                <p>Please scan the QR code from the desktop app.</p>
            </body>
        </html>
        """, 400
    
    logger.info(f"Upload page accessed for session: {session_id}")
    return render_template('upload.html', session_id=session_id)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'active_sessions': len(active_sessions)
    })

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")
    
    # Remove from active sessions if it was a desktop
    sessions_to_remove = [sid for sid, desktop_sid in active_sessions.items() if desktop_sid == request.sid]
    for session_id in sessions_to_remove:
        del active_sessions[session_id]
        logger.info(f"Removed session: {session_id}")

@socketio.on('register_desktop')
def handle_register_desktop(data):
    """Register desktop client"""
    session_id = data.get('session_id')
    if session_id:
        join_room(f"desktop_{session_id}")
        active_sessions[session_id] = request.sid
        logger.info(f"Desktop registered for session: {session_id} (sid: {request.sid})")
        emit('registration_success', {'message': 'Desktop registered successfully'})
    else:
        emit('registration_error', {'message': 'No session ID provided'})

@socketio.on('register_mobile')
def handle_register_mobile(data):
    """Register mobile client"""
    session_id = data.get('session_id')
    if session_id:
        join_room(f"mobile_{session_id}")
        logger.info(f"Mobile registered for session: {session_id} (sid: {request.sid})")
        
        # Check if desktop is connected
        if session_id in active_sessions:
            emit('registration_success', {'message': 'Connected to desktop'})
        else:
            emit('registration_error', {'message': 'Desktop not found. Please check if the app is running.'})
    else:
        emit('registration_error', {'message': 'No session ID provided'})

@socketio.on('upload_photo')
def handle_upload(data):
    """Handle photo upload from mobile"""
    session_id = data.get('session_id')
    photo_data = data.get('photo')
    mime_type = data.get('mime_type', 'image/jpeg')
    file_size = data.get('file_size', 0)
    
    logger.info(f"Photo upload request from session: {session_id}, size: {file_size} bytes")
    
    # Validate session
    if not session_id or session_id not in active_sessions:
        logger.warning(f"Invalid session or desktop not connected: {session_id}")
        emit('upload_error', {'message': 'Desktop not connected. Please ensure the desktop app is running.'})
        return
    
    # Validate data
    if not photo_data:
        logger.warning("No photo data received")
        emit('upload_error', {'message': 'No photo data received'})
        return
    
    # Validate file type
    allowed_types = {'image/jpeg', 'image/png', 'image/jpg', 'image/webp'}
    if mime_type not in allowed_types:
        logger.warning(f"Invalid file type: {mime_type}")
        emit('upload_error', {'message': f'Invalid file type: {mime_type}'})
        return
    
    # Validate file size
    max_size = 10 * 1024 * 1024  # 10MB
    if file_size > max_size:
        logger.warning(f"File too large: {file_size} bytes")
        emit('upload_error', {'message': 'File too large (max 10MB)'})
        return
    
    # Forward to desktop
    try:
        socketio.emit('photo_received', {
            'photo': photo_data,
            'mime_type': mime_type,
            'file_size': file_size
        }, room=f"desktop_{session_id}")
        
        logger.info(f"Photo successfully relayed to desktop for session: {session_id}")
        
        # Confirm to mobile
        emit('upload_success', {'message': 'Photo sent successfully'})
        
    except Exception as e:
        logger.error(f"Error relaying photo: {str(e)}")
        emit('upload_error', {'message': 'Failed to send photo to desktop'})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)