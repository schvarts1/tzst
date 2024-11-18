import sqlite3
import os
import hashlib
import random
import time
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'supersecretkey'
socketio = SocketIO(app)

# Directory for file uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = 'discord_clone.db'


# Initialize SQLite database
def init_db():
    conn = sqlite3.connect(DATABASE)
    with conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY,
                            username TEXT UNIQUE,
                            password TEXT,
                            role TEXT DEFAULT 'Member',
                            status TEXT DEFAULT 'Offline',
                            avatar TEXT DEFAULT '👤',
                            bio TEXT DEFAULT ''
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY,
                            sender TEXT,
                            content TEXT,
                            timestamp INTEGER,
                            channel TEXT,
                            reactions TEXT DEFAULT '',
                            pinned INTEGER DEFAULT 0,
                            edited INTEGER DEFAULT 0
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS channels (
                            id INTEGER PRIMARY KEY,
                            name TEXT UNIQUE,
                            server TEXT,
                            topic TEXT DEFAULT '',
                            description TEXT DEFAULT '',
                            is_private INTEGER DEFAULT 0,
                            owner TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS servers (
                            id INTEGER PRIMARY KEY,
                            name TEXT UNIQUE,
                            owner TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS direct_messages (
                            id INTEGER PRIMARY KEY,
                            sender TEXT,
                            receiver TEXT,
                            message TEXT,
                            timestamp INTEGER
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS invites (
                            id INTEGER PRIMARY KEY,
                            code TEXT UNIQUE,
                            channel TEXT,
                            sender TEXT,
                            expiration INTEGER
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS roles (
                            id INTEGER PRIMARY KEY,
                            server TEXT,
                            role_name TEXT,
                            permissions TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_status (
                            id INTEGER PRIMARY KEY,
                            username TEXT,
                            status TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                            id INTEGER PRIMARY KEY,
                            username TEXT,
                            channel TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS custom_emotes (
                            id INTEGER PRIMARY KEY,
                            server TEXT,
                            emote_name TEXT,
                            emote_image TEXT
                        )''')


init_db()


# Helper function to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# HTML template for the app
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Complete Discord Clone</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #2c2f33; color: #ffffff; }
        #sidebar { float: left; width: 20%; background: #23272a; padding: 10px; }
        #main { float: right; width: 75%; padding: 10px; }
        #chat { height: 300px; overflow-y: scroll; background: #2c2f33; padding: 10px; }
        #messages { list-style-type: none; padding: 0; }
        input, button { margin: 5px; padding: 10px; width: 90%; }
        .reaction { cursor: pointer; margin: 0 5px; }
        .mention { color: #7289da; }
        .edited { font-style: italic; color: #b9bbbe; }
        .pinned { color: gold; }
        .status { font-size: 14px; color: #7289da; }
        .user-list { padding: 10px; background: #23272a; margin-top: 20px; }
        .login-form { max-width: 300px; margin: 100px auto; padding: 20px; background: #2f3136; border-radius: 8px; }
        .login-form input { width: 100%; margin: 10px 0; padding: 10px; }
    </style>
</head>
<body>
    <div id="sidebar">
        <h2>Channels</h2>
        <div id="channels"></div>
        <button onclick="createChannel()">Create Channel</button>
        <h3>Voice Channels</h3>
        <div id="voiceChannels"></div>
        <button onclick="createVoiceChannel()">Create Voice Channel</button>
        <h3>Users</h3>
        <div id="userList"></div>
        <button onclick="createServer()">Create Server</button>
    </div>
    <div id="main">
        <h2>Chat</h2>
        <div id="chat">
            <ul id="messages"></ul>
        </div>
        <input id="message" placeholder="Type a message..." oninput="typing()">
        <button onclick="sendMessage()">Send</button>
        <button onclick="pinMessage()">Pin Message</button>
        <input type="file" id="fileInput">
        <button onclick="uploadFile()">Upload File</button>
        <h3>Reactions</h3>
        <div id="emotes"></div>
        <div id="typing"></div>
    </div>

    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
    <script>
        const socket = io();
        let currentChannel = 'general';

        socket.on('load_channels', (channels) => {
            const channelList = document.getElementById('channels');
            channelList.innerHTML = '';
            channels.forEach(channel => {
                const div = document.createElement('div');
                div.textContent = channel.name;
                div.onclick = () => joinChannel(channel.name);
                channelList.appendChild(div);
            });
        });

        socket.on('load_voice_channels', (voiceChannels) => {
            const voiceChannelList = document.getElementById('voiceChannels');
            voiceChannelList.innerHTML = '';
            voiceChannels.forEach(vc => {
                const div = document.createElement('div');
                div.textContent = vc.name;
                div.onclick = () => joinVoiceChannel(vc.name);
                voiceChannelList.appendChild(div);
            });
        });

        socket.on('load_messages', (messages) => {
            const messageList = document.getElementById('messages');
            messageList.innerHTML = '';
            messages.forEach(msg => {
                const li = document.createElement('li');
                li.innerHTML = (msg.pinned ? `<span class="pinned">[Pinned]</span>` : '') + `${msg.sender}: ${msg.content} ${msg.edited ? '<span class="edited">(edited)</span>' : ''}`;
                messageList.appendChild(li);
            });
        });

        socket.on('receive_message', (data) => {
            const li = document.createElement('li');
            li.innerHTML = (data.pinned ? `<span class="pinned">[Pinned]</span>` : '') + `${data.sender}: ${data.content}`;
            document.getElementById('messages').appendChild(li);
        });

        socket.on('emote_list', (emotes) => {
            const emoteList = document.getElementById('emotes');
            emoteList.innerHTML = '';
            emotes.forEach(emote => {
                const emoteBtn = document.createElement('button');
                emoteBtn.textContent = emote.name;
                emoteBtn.onclick = () => addReaction(emote.name);
                emoteList.appendChild(emoteBtn);
            });
        });

        socket.on('online_users', (users) => {
            const userList = document.getElementById('userList');
            userList.innerHTML = '';
            users.forEach(user => {
                const userDiv = document.createElement('div');
                userDiv.textContent = user.username + ' - ' + user.status;
                userList.appendChild(userDiv);
            });
        });

        function createChannel() {
            const name = prompt('Enter channel name:');
            const topic = prompt('Enter topic for the channel:');
            const description = prompt('Enter a description for the channel:');
            socket.emit('create_channel', { name, topic, description });
        }

        function createVoiceChannel() {
            const name = prompt('Enter voice channel name:');
            socket.emit('create_voice_channel', { name });
        }

        function sendMessage() {
            const message = document.getElementById('message').value;
            socket.emit('send_message', { channel: currentChannel, message });
            document.getElementById('message').value = '';
        }

        function pinMessage() {
            const message = document.getElementById('message').value;
            socket.emit('pin_message', { channel: currentChannel, message });
        }

        function uploadFile() {
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            if (file) {
                const formData = new FormData();
                formData.append('file', file);
                fetch('/upload', { method: 'POST', body: formData })
                    .then(response => response.json())
                    .then(data => {
                        socket.emit('send_message', { channel: currentChannel, message: data.url });
                    });
            }
        }

        function typing() {
            socket.emit('user_typing', { username: 'User', channel: currentChannel });
        }

        function addReaction(emote) {
            const message = document.getElementById('message').value;
            socket.emit('add_reaction', { channel: currentChannel, message, emote });
        }

        function joinChannel(channel) {
            currentChannel = channel;
            socket.emit('join_channel', { channel });
        }

        function createServer() {
            const serverName = prompt('Enter server name:');
            socket.emit('create_server', { name: serverName });
        }
    </script>
</body>
</html>
"""

# SocketIO Events
@socketio.on('create_channel')
def create_channel(data):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO channels (name, server, owner, topic, description) VALUES (?, ?, ?, ?, ?)',
                   (data['name'], 'general', 'admin', data['topic'], data['description']))
    conn.commit()
    emit('load_channels', list_channels(), broadcast=True)

@socketio.on('create_voice_channel')
def create_voice_channel(data):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO channels (name, server, owner) VALUES (?, ?, ?)', (data['name'], 'voice', 'admin'))
    conn.commit()
    emit('load_voice_channels', list_channels(), broadcast=True)

@socketio.on('send_message')
def send_message(data):
    conn = sqlite3.connect(DATABASE)
    timestamp = int(time.time())
    conn.execute('INSERT INTO messages (channel, sender, content, timestamp) VALUES (?, ?, ?, ?)', 
                 (data['channel'], 'User', data['message'], timestamp))
    conn.commit()
    emit('receive_message', {'sender': 'User', 'content': data['message'], 'pinned': False, 'edited': False}, broadcast=True)

@socketio.on('pin_message')
def pin_message(data):
    conn = sqlite3.connect(DATABASE)
    conn.execute('UPDATE messages SET pinned = 1 WHERE channel = ? AND content = ?', (data['channel'], data['message']))
    conn.commit()
    emit('load_messages', get_messages(data['channel']), broadcast=True)

@socketio.on('add_reaction')
def add_reaction(data):
    conn = sqlite3.connect(DATABASE)
    conn.execute('UPDATE messages SET reactions = reactions || ? WHERE channel = ? AND content = ?',
                 (data['emote'], data['channel'], data['message']))
    conn.commit()
    emit('load_messages', get_messages(data['channel']), broadcast=True)

# Helper functions
def list_channels():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.execute('SELECT name FROM channels')
    return [{'name': row[0]} for row in cursor.fetchall()]

def get_messages(channel):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.execute('SELECT sender, content, pinned, edited FROM messages WHERE channel = ? ORDER BY timestamp DESC', (channel,))
    return [{'sender': row[0], 'content': row[1], 'pinned': row[2], 'edited': row[3]} for row in cursor.fetchall()]

if __name__ == '__main__':
    socketio.run(app, port=random.randint(5000, 6000))
