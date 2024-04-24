from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
import os
from datetime import datetime, timedelta
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'  # Папка для сохранения загруженных фотографий
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Максимальный размер загружаемых файлов (16 МБ)
socketio = SocketIO(app)

messages = []
MESSAGE_LIFETIME = 60  # Время жизни сообщения в секундах по умолчанию
connected_users = {}

def set_message_lifetime(lifetime):
    global MESSAGE_LIFETIME
    MESSAGE_LIFETIME = lifetime
    emit('message_lifetime_updated', lifetime, broadcast=True)  # Отправляем обновленное значение всем клиентам

def remove_expired_messages():
    now = datetime.now()
    expired_messages = [msg for msg in messages if now - msg['timestamp'] >= timedelta(seconds=MESSAGE_LIFETIME)]
    messages[:] = [msg for msg in messages if now - msg['timestamp'] < timedelta(seconds=MESSAGE_LIFETIME)]

    for msg in expired_messages:
        emit('expire_message', msg['message'], broadcast=True)

    socketio.start_background_task(remove_expired_messages, 1)  # Запускать функцию каждую секунду

remove_expired_messages()

def logout_user(username):
    for socket_id, user in connected_users.items():
        if user == username:
            del connected_users[socket_id]
            system_message = f"Пользователь {username} покинул чат"
            emit('new_message', {'message': system_message, 'timestamp': datetime.now().timestamp(), 'username': 'Система'}, broadcast=True, include_self=False)
            break

@socketio.on('set_message_lifetime')
def handle_set_message_lifetime(data):
    lifetime = data.get('lifetime')
    username = data.get('username')
    if lifetime is not None and username is not None:
        set_message_lifetime(lifetime)
        emit('message_lifetime_updated', lifetime, broadcast=True)
        system_message = f"Время жизни сообщений изменено на {lifetime} секунд пользователем {username}"
        emit('new_message', {'message': system_message, 'timestamp': datetime.now().timestamp(), 'username': 'Система'}, broadcast=True, include_self=False)

@app.route('/')
def index():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(project_dir, 'index.html')

@socketio.on('login')
def handle_login(data):
    username = data.get('username')
    socket_id = request.sid
    if username and socket_id:
        connected_users[socket_id] = username
        system_message = f"Пользователь {username} подключился к чату"
        emit('new_message', {'message': system_message, 'timestamp': datetime.now().timestamp(), 'username': 'Система'}, broadcast=True, include_self=False)
        # Отправляем все предыдущие сообщения новому пользователю
        for msg in messages:
            emit('new_message', msg, room=socket_id)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')
    socket_id = request.sid
    username = connected_users.get(socket_id)
    if username:
        del connected_users[socket_id]
        system_message = f"Пользователь {username} покинул чат"
        emit('new_message', {'message': system_message, 'timestamp': datetime.now().timestamp(), 'username': 'Система'}, broadcast=True, include_self=False)
        
@socketio.on('send_message')
def handle_send_message(data):
    message = data['message']
    image_data = data.get('image')  # Получаем данные фотографии (если есть)
    socket_id = request.sid
    username = connected_users.get(socket_id)
    if username:
        timestamp = datetime.now()
        new_message = {'message': message, 'timestamp': timestamp.timestamp(), 'username': username}
        if image_data:
            # Сохраняем фотографию на сервере
            image_filename = f"{timestamp.strftime('%Y%m%d%H%M%S')}.jpg"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            with open(image_path, 'wb') as f:
                f.write(base64.b64decode(image_data.split(',')[1]))
            new_message['image_url'] = f"/uploads/{image_filename}"
        messages.append(new_message)
        print(f"New message: {new_message}")
        for user_socket_id, user_username in connected_users.items():
            if user_username:
                emit('new_message', new_message, room=user_socket_id)

@socketio.on('clear_messages')
def handle_clear_messages(data):
    username = data.get('username')
    if username:
        messages.clear()  # Очищаем список сообщений
        if connected_users:  # Проверяем, есть ли подключенные пользователи
            system_message = "Привет! Как дела?"
            emit('clear_messages', system_message, broadcast=True)
        logout_user(username)  # Разлогиниваем пользователя

@app.route('/uploads/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=443)