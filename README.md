# LAN Multi-User Communication System
## Technical Documentation

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Installation & Setup](#installation--setup)
3. [Communication Protocols](#communication-protocols)
4. [AI Assistant](#ai-assistant)
5. [User Guide](#user-guide)
6. [Troubleshooting](#troubleshooting)

---

## System Overview

The LAN Multi-User Communication System enables real-time collaboration on local networks through video conferencing, audio streaming, screen sharing, group chat, and file transfer.

### Key Features
- **Video Conferencing**: Multi-user video streaming (320×240, 30 FPS)
- **Audio Communication**: Full-duplex voice (16kHz mono PCM)
- **Screen Sharing**: Live desktop presentation (10 FPS)
- **Group Chat**: Persistent messages with timestamps
- **File Sharing**: Upload/download between participants
- **AI Assistant**: Query Llama-3.2 via Hugging Face API
- **User Management**: Automatic session tracking

### System Requirements
- Python 3.8+
- Local Area Network (LAN)
- Webcam, microphone, speakers
- 2GB RAM minimum

---

## Installation & Setup

### Step 1: Install Dependencies

```bash
cd lan-communication-system
pip install -r requirements.txt
```

### Step 2: Get Server IP

**Linux/macOS:**
```bash
hostname -I
```

**Windows:**
```bash
ipconfig
```

Note your server IP (e.g., `192.168.1.100`)

### Step 3: Start Server

```bash
python3 server.py
```

**Output:**
```
==================================================
LAN Communication Server
==================================================
Server IP: 192.168.1.100
TCP Port: 5555
UDP Port: 5556
==================================================
```

### Step 4: Start Clients

On each client machine:
```bash
python3 client.py
```

Fill in connection dialog:
- **Username**: Your name
- **Server IP**: From Step 2
- **TCP Port**: 5555
- **UDP Port**: 5556
- Click **Connect**

---

## User Guide

### Interface Layout

**Top: Video Conference**
- Grid of all video streams (max 3 columns)
- **Start Video** / **Start Audio** buttons
- Username label on each stream

**Middle: Screen Sharing**
- **Start Presenting** / **Stop Presenting**
- One presenter at a time
- 10 FPS refresh rate

**Bottom: Users, Chat, Files**
- Left: Connected users list
- Center: Chat input and history
- Right: File upload/download

### Features

#### Video Conferencing
1. Click **Start Video**
2. Grant camera permission
3. Your video appears in grid
4. Others' videos appear as they stream

#### Audio
1. Click **Start Audio**
2. Speak naturally (broadcasts to all)
3. Hear others through speakers
4. Use headphones to avoid feedback

#### Screen Sharing
1. Click **Start Presenting**
2. Your desktop streams to all participants
3. Only one presenter allowed
4. Click **Stop Presenting** when done

#### Chat
1. Type message in input field
2. Press Enter or click **Send**
3. Message broadcasts with timestamp
4. New users receive full history on join

#### File Transfer
**Upload:**
1. Click **Upload File**
2. Select file
3. All users receive notification

**Download:**
1. Select file in file list
2. Click **Download Selected**
3. Choose save location

---

## Troubleshooting

### Connection
- **"Connection refused"** → Server not running or wrong IP/port
- **"Connection timeout"** → Network issue; test with `ping [server_ip]`

### Video
- **"Cannot access webcam"** → Grant Camera permission in System Preferences
- **Black screen** → Try different USB port, restart app
- **Choppy video** → Use wired connection, close other apps

### Audio
- **"No audio devices"** → Check with `python3 -c "import pyaudio; print(pyaudio.PyAudio().get_device_count())"`
- **"Device in use"** → Close Zoom, Teams, or other audio apps
- **No sound** → Check speaker volume and connection
- **Echo/feedback** → Use headphones instead of speakers

### Chat & Files
- **Messages not appearing** → Check connection status
- **File upload fails** → Try smaller file, verify stable connection
- **Corrupted download** → Download again

---

## AI Assistant

The Personal Assistant integrates **Hugging Face Inference API** with **Llama-3.2-3B-Instruct** language model.

### Setup AI Assistant

1. Create account at [huggingface.co](https://huggingface.co)
2. Generate API token: Settings → Access Tokens
3. Update `client.py` line ~45:

```python
HF_HEADERS = {"Authorization": "Bearer YOUR_TOKEN_HERE"}
```

### Using AI Assistant

Click **Personal Assistant** button in chat panel to open AI dialog.

#### Two Features:

**1. Chat with AI**
- Ask questions and get instant answers
- Type query and press Enter
- AI responds within 3-10 seconds
- Max response: 300 tokens

**Example queries:**
```
- "What is machine learning?"
- "Explain this concept"
- "How do I use this app?"
```

**2. Summarize Group Chat**
- Automatically summarizes all group messages
- Highlights key discussions and interactions
- Click **Summarize Chats** button
- AI analyzes chat history and generates summary

### API Integration Details

```python
def query_model(self, prompt: str, timeout: int = 30):
    """Send request to Hugging Face model"""
    
    payload = {
        "model": "meta-llama/Llama-3.2-3B-Instruct",
        "messages": [
            {"role": "system", "content": "You are an assistant"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
        "temperature": 0.0,  # Deterministic responses
    }
    
    resp = requests.post(
        "https://router.huggingface.co/v1/chat/completions",
        headers=self.HF_HEADERS,
        json=payload,
        timeout=timeout
    )
    
    return resp.json()['choices'][0]['message']['content']
```

### Troubleshooting AI

**"HF request failed: 401"**
- Invalid or missing API token
- Solution: Generate new token and update `HF_HEADERS`

**Slow responses (30+ seconds)**
- API server slow or network latency
- Solution: Check internet connection

---

## Communication Protocols

### TCP Protocol (Reliable)

**Purpose:** Control, chat, file transfer

**Format:** Length-prefixed JSON
```
[4 bytes: length] [JSON payload]
```

**Message Examples:**

```json
{
  "type": "register",
  "username": "alice",
  "udp_port": 54321
}
```

```json
{
  "type": "chat",
  "username": "alice",
  "message": "Hello everyone",
  "timestamp": "14:25:30"
}
```

```json
{
  "type": "file_upload",
  "filename": "report.pdf",
  "filesize": 2048576,
  "filedata": "[base64-encoded]"
}
```

### UDP Protocol (Real-time Streams)

**Purpose:** Video and audio (low-latency)

**Packet Structure:**
```
[1 byte: type] [1 byte: username_len] [username] [payload]
```

| Type | Description |
|------|-------------|
| 1 | Video frame (JPEG) |
| 2 | Audio packet (PCM) |

**Video Specs:**
- Codec: JPEG
- Resolution: 320×240
- Frame Rate: 30 FPS
- Quality: 40% (adaptive)
- Max Packet: 65 KB

**Audio Specs:**
- Format: PCM 16-bit mono
- Sample Rate: 16 kHz
- Chunk: 2,048 samples (128ms)

---


## Advanced Config

### Custom Ports
```bash
python3 server.py 8888 8889
```

### SSL/TLS Encryption
```python
import ssl

context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain('server.crt', 'server.key')
self.tcp_socket = context.wrap_socket(tcp_socket, server_side=True)
```

### Persistent Chat History
```python
def save_chat_history(self):
    with open('chat_history.json', 'w') as f:
        json.dump(self.chat_history, f, indent=2)
```

---

## Conclusion

Complete documentation for LAN collaboration. For support, check terminal output for error messages.

**Happy communicating!**
