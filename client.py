#!/usr/bin/env python3
"""
LAN Multi-User Communication Client
Full-featured GUI client with video, audio, screen sharing, chat, and file transfer
"""

import socket
import threading
import struct
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk
import pyaudio
import base64
import io
import os
from datetime import datetime
import mss
import time
import requests

class LANClient:
    def __init__(self, master):
        self.master = master
        self.master.title("LAN Communication System")
        self.master.geometry("1200x800")
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Connection state
        self.connected = False
        self.username = None
        self.server_ip = None
        self.server_tcp_port = 5555
        self.server_udp_port = 5556
        self.tcp_socket = None
        self.udp_socket = None
        self.udp_port = 0
        
        # Streaming state
        self.video_streaming = False
        self.audio_streaming = False
        self.presenting = False
        self.presenter = None
        
        # Video components
        self.video_cap = None
        self.video_frames = {}  # {username: frame}
        
        # Audio components
        self.audio = pyaudio.PyAudio()
        self.audio_input_stream = None
        self.audio_output_stream = None
        
        # Users list
        self.users = []
        
        # Chat history for summarization
        self.chat_history = []
        
        # Running flag
        self.running = True
        
        # Build UI
        self.build_connection_ui()

        # --- Hugging Face Inference API configuration ---
    HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
    HF_MODEL = "meta-llama/Llama-3.2-3B-Instruct"
    HF_HEADERS = {"Authorization": "Bearer "}

    def query_model(self, prompt: str, timeout: int = 30):
        """Send request to Hugging Face model and return response text."""
        payload = {
            "model": self.HF_MODEL,
            "messages": [
                {"role": "system", "content": "You are a assistant like siri or google assistant only answer questions the user asks."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.0,
        }

        resp = requests.post(self.HF_API_URL, headers=self.HF_HEADERS, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise Exception(f'HF request failed: {resp.status_code} - {resp.text}')

        data = resp.json()

        # Try common response shapes: choices[0].message.content or choices[0].text
        text = None
        try:
            choices = data.get('choices') or []
            if choices:
                first = choices[0]
                # Chat completions style
                msg = first.get('message') or {}
                text = msg.get('content')
                if not text:
                    text = first.get('text')
        except Exception:
            text = None

        if not text:
            # Fallback to entire JSON as string
            text = str(data)

        return text
    
    def build_connection_ui(self):
        """Build connection dialog"""
        frame = ttk.Frame(self.master, padding="20")
        frame.pack(expand=True)
        
        ttk.Label(frame, text="LAN Communication System", font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=2, pady=10)
        
        ttk.Label(frame, text="Username:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.username_entry = ttk.Entry(frame, width=30)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(frame, text="Server IP:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.server_entry = ttk.Entry(frame, width=30)
        self.server_entry.grid(row=2, column=1, padx=5, pady=5)
        self.server_entry.insert(0, "192.168.1.100")
        
        ttk.Label(frame, text="TCP Port:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.tcp_port_entry = ttk.Entry(frame, width=30)
        self.tcp_port_entry.grid(row=3, column=1, padx=5, pady=5)
        self.tcp_port_entry.insert(0, "5555")
        
        ttk.Label(frame, text="UDP Port:").grid(row=4, column=0, sticky='e', padx=5, pady=5)
        self.udp_port_entry = ttk.Entry(frame, width=30)
        self.udp_port_entry.grid(row=4, column=1, padx=5, pady=5)
        self.udp_port_entry.insert(0, "5556")
        
        self.connect_btn = ttk.Button(frame, text="Connect", command=self.connect_to_server)
        self.connect_btn.grid(row=5, column=0, columnspan=2, pady=20)
        
        self.status_label = ttk.Label(frame, text="", foreground="red")
        self.status_label.grid(row=6, column=0, columnspan=2)
    def send_message(self, data):
     """Send a JSON message via TCP to the server"""
     if self.tcp_socket:
        try:
            msg = json.dumps(data).encode('utf-8')
            # Send message length first
            self.tcp_socket.sendall(struct.pack('>I', len(msg)) + msg)
        except Exception as e:
            print(f"Send message error: {e}")

    def recv_message(self):
     """Receive a JSON message via TCP from the server"""
     if self.tcp_socket:
        try:
            # First, read 4 bytes for message length
            raw_len = self.tcp_socket.recv(4)
            if not raw_len:
                return None
            msg_len = struct.unpack('>I', raw_len)[0]
            # Then read the actual message
            data = b''
            while len(data) < msg_len:
                packet = self.tcp_socket.recv(msg_len - len(data))
                if not packet:
                    return None
                data += packet
            return json.loads(data.decode('utf-8'))
        except Exception as e:
            print(f"Receive message error: {e}")
            return None

    def connect_to_server(self):
        """Connect to server"""
        self.username = self.username_entry.get().strip()
        self.server_ip = self.server_entry.get().strip()
        
        if not self.username or not self.server_ip:
            self.status_label.config(text="Please enter username and server IP")
            return
        
        try:
            self.server_tcp_port = int(self.tcp_port_entry.get())
            self.server_udp_port = int(self.udp_port_entry.get())
            tcp_port = self.server_tcp_port
            udp_port = self.server_udp_port
            
            self.status_label.config(text="Connecting...", foreground="blue")
            self.master.update()
            
            # Create TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((self.server_ip, tcp_port))
            
            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('', 0))  # Bind to any available port
            self.udp_port = self.udp_socket.getsockname()[1]
            
            # Register with server
            self.send_message({
                'type': 'register',
                'username': self.username,
                'udp_port': self.udp_port
            })
            
            # Wait for registration response
            response = self.recv_message()
            if response and response['type'] == 'registered':
                self.connected = True
                self.users = response['users']
                self.presenter = response.get('presenter')
                
                # Build main UI
                self.build_main_ui()
                
                # Load chat history
                for msg in response.get('chat_history', []):
                    self.display_chat_message(msg)
                
                # Start receiver threads
                threading.Thread(target=self.receive_tcp_messages, daemon=True).start()
                threading.Thread(target=self.receive_udp_streams, daemon=True).start()
                
                print(f"Connected to server as {self.username}")
            else:
                raise Exception("Registration failed")
                
        except Exception as e:
            self.status_label.config(text=f"Connection failed: {e}", foreground="red")
            if self.tcp_socket:
                self.tcp_socket.close()
            if self.udp_socket:
                self.udp_socket.close()
    
    def build_main_ui(self):
        """Build main application UI"""
        # Clear connection UI
        for widget in self.master.winfo_children():
            widget.destroy()
        
        # Create main layout
        # Top: Video grid
        video_frame = ttk.LabelFrame(self.master, text="Video Conference", padding="5")
        video_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.video_container = ttk.Frame(video_frame)
        self.video_container.pack(fill=tk.BOTH, expand=True)
        
        # Video controls
        video_controls = ttk.Frame(video_frame)
        video_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        self.video_btn = ttk.Button(video_controls, text="Start Video", command=self.toggle_video)
        self.video_btn.pack(side=tk.LEFT, padx=5)
        
        self.audio_btn = ttk.Button(video_controls, text="Start Audio", command=self.toggle_audio)
        self.audio_btn.pack(side=tk.LEFT, padx=5)
        
        # Middle: Screen sharing
        screen_frame = ttk.LabelFrame(self.master, text="Screen Sharing", padding="5")
        screen_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.screen_label = ttk.Label(screen_frame, text="No presentation active", anchor=tk.CENTER)
        self.screen_label.pack(fill=tk.BOTH, expand=True)
        
        screen_controls = ttk.Frame(screen_frame)
        screen_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        self.present_btn = ttk.Button(screen_controls, text="Start Presenting", command=self.toggle_presenting)
        self.present_btn.pack(side=tk.LEFT, padx=5)
        
        # Bottom: Chat and controls
        bottom_frame = ttk.Frame(self.master)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left: Users list
        users_frame = ttk.LabelFrame(bottom_frame, text="Users", padding="5")
        users_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)
        
        self.users_listbox = tk.Listbox(users_frame, width=20)
        self.users_listbox.pack(fill=tk.BOTH, expand=True)
        self.update_users_list()
        
        # Center: Chat
        chat_frame = ttk.LabelFrame(bottom_frame, text="Group Chat", padding="5")
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.chat_display = scrolledtext.ScrolledText(chat_frame, height=10, state=tk.DISABLED, wrap=tk.WORD)
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        chat_input_frame = ttk.Frame(chat_frame)
        chat_input_frame.pack(fill=tk.X, pady=5)
        
        self.chat_entry = ttk.Entry(chat_input_frame)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.chat_entry.bind('<Return>', lambda e: self.send_chat())
        
        ttk.Button(chat_input_frame, text="Send", command=self.send_chat).pack(side=tk.LEFT)

        # Chat Bot button (opens dialog)
        ttk.Button(chat_frame, text="Personal Assistant", command=self.open_hf_dialog).pack(fill=tk.X, pady=4)
        
        # Right: File sharing
        file_frame = ttk.LabelFrame(bottom_frame, text="File Sharing", padding="5")
        file_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)
        
        ttk.Button(file_frame, text="Upload File", command=self.upload_file).pack(fill=tk.X, pady=2)
        
        self.files_listbox = tk.Listbox(file_frame, width=25, height=8)
        self.files_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        
        ttk.Button(file_frame, text="Download Selected", command=self.download_file).pack(fill=tk.X, pady=2)
        
        # Initialize video display
        self.update_video_grid()
    
    def toggle_video(self):
        """Toggle video streaming"""
        if not self.video_streaming:
            try:
                # Try to open camera with proper backend
                self.video_cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)  # macOS specific
                
                # Wait a bit for camera to initialize
                time.sleep(0.5)
                
                if not self.video_cap.isOpened():
                    # Try again without backend specification
                    self.video_cap = cv2.VideoCapture(0)
                    time.sleep(0.5)
                
                if not self.video_cap.isOpened():
                    messagebox.showerror("Error", 
                        "Cannot access webcam.\n\n" +
                        "Please grant Camera permission:\n" +
                        "System Preferences → Security & Privacy → Camera\n" +
                        "Enable for Terminal/Python, then restart the client.")
                    return
                
                # Test read
                ret, test_frame = self.video_cap.read()
                if not ret or test_frame is None:
                    messagebox.showerror("Error", "Camera opened but cannot read frames. Try restarting the client.")
                    self.video_cap.release()
                    return
                
                self.video_streaming = True
                # Update button in main thread
                self.master.after(0, lambda: self.video_btn.config(text="Stop Video"))
                threading.Thread(target=self.stream_video, daemon=True).start()
                print(f"✅ Video started successfully for {self.username}")
            except Exception as e:
                messagebox.showerror("Error", f"Video error: {e}\n\nTry restarting the client.")
                if self.video_cap:
                    try:
                        self.video_cap.release()
                    except:
                        pass
        else:
            # Stop video streaming
            self.video_streaming = False
            
            # Wait for thread to notice
            time.sleep(0.2)
            
            # Update button in main thread
            self.master.after(0, lambda: self.video_btn.config(text="Start Video"))
            
            # Safely close camera in separate thread
            threading.Thread(target=self._close_camera, daemon=True).start()
            
            # Remove own video from display
            if self.username in self.video_frames:
                del self.video_frames[self.username]
            
            print(f"Video stopped for {self.username}")
    
    def _close_camera(self):
        """Safely close camera without blocking"""
        try:
            if self.video_cap:
                try:
                    self.video_cap.release()
                except Exception as e:
                    print(f"Camera close error: {e}")
                self.video_cap = None
        except Exception as e:
            print(f"Error closing camera: {e}")
    
    def stream_video(self):
        """Stream video to server"""
        print(f"📹 Starting video stream for {self.username}")
        frame_count = 0
        error_count = 0
        
        while self.video_streaming and self.running:
            try:
                ret, frame = self.video_cap.read()
                if not ret or frame is None:
                    error_count += 1
                    if error_count > 10:
                        print(f"⚠️ Camera read failed multiple times, stopping video")
                        self.video_streaming = False
                        break
                    time.sleep(0.1)
                    continue
                
                error_count = 0  # Reset on successful read
                
                # Resize and compress MORE to avoid UDP packet size limit (65507 bytes)
                frame = cv2.resize(frame, (320, 240))
                
                # Try higher compression first
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, 40]  # Lower quality = smaller
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                
                # Check size and reduce if needed
                if len(buffer) > 60000:  # Safety margin
                    encode_param = [cv2.IMWRITE_JPEG_QUALITY, 30]
                    _, buffer = cv2.imencode('.jpg', frame, encode_param)
                
                if len(buffer) > 60000:  # Still too big, resize smaller
                    frame = cv2.resize(frame, (240, 180))
                    encode_param = [cv2.IMWRITE_JPEG_QUALITY, 40]
                    _, buffer = cv2.imencode('.jpg', frame, encode_param)
                
                # Create packet: type(1) + username_len(1) + username + frame_data
                username_bytes = self.username.encode('utf-8')
                packet = bytes([1, len(username_bytes)]) + username_bytes + buffer.tobytes()
                
                # Final size check
                if len(packet) > 65000:
                    print(f"⚠️ Packet too large ({len(packet)} bytes), skipping frame")
                    continue
                
                # Send via UDP (using stored port, not GUI widget)
                self.udp_socket.sendto(packet, (self.server_ip, self.server_udp_port))
                
                # Update own video (thread-safe) - resize back for display
                display_frame = cv2.resize(frame, (320, 240))
                self.video_frames[self.username] = display_frame.copy()
                
                frame_count += 1
                if frame_count % 90 == 0:  # Log every 90 frames (3 seconds)
                    print(f"📹 Sent {frame_count} video frames")
                
                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                # Only print error once, not repeatedly
                if frame_count % 30 == 0:
                    print(f"Video stream error: {e}")
                time.sleep(0.1)
        
        print(f"📹 Video stream stopped for {self.username}")
    
    def toggle_audio(self):
        """Toggle audio streaming"""
        if not self.audio_streaming:
            try:
                # Check if audio device is available
                if self.audio.get_device_count() == 0:
                    messagebox.showerror("Error", "No audio devices found")
                    return
                
                print(f"🎤 Opening audio devices for {self.username}...")
                
                # Get default devices
                try:
                    default_input = self.audio.get_default_input_device_info()
                    default_output = self.audio.get_default_output_device_info()
                    print(f"   Input device: {default_input['name']}")
                    print(f"   Output device: {default_output['name']}")
                except Exception as e:
                    print(f"   Warning: Could not get default device info: {e}")
                
                # Input stream (microphone) - with better error handling
                try:
                    self.audio_input_stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=2048,
                        input_device_index=None,  # Use default
                        stream_callback=None
                    )
                    print(f"   ✓ Microphone opened")
                except Exception as e:
                    raise Exception(f"Microphone error: {e}")
                
                # Output stream (speakers)
                try:
                    self.audio_output_stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        output=True,
                        frames_per_buffer=2048,
                        output_device_index=None,  # Use default
                        stream_callback=None
                    )
                    print(f"   ✓ Speakers opened")
                except Exception as e:
                    # Close input stream if output fails
                    if self.audio_input_stream:
                        try:
                            self.audio_input_stream.close()
                        except:
                            pass
                    raise Exception(f"Speaker error: {e}")
                
                self.audio_streaming = True
                # Update button in main thread
                self.master.after(0, lambda: self.audio_btn.config(text="Stop Audio"))
                threading.Thread(target=self.stream_audio, daemon=True).start()
                print(f"🎤 Audio started successfully for {self.username}")
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Audio error: {e}")
                
                if "already in use" in error_msg.lower() or "device unavailable" in error_msg.lower():
                    self.master.after(0, lambda: messagebox.showerror("Error", 
                        "Audio device is busy.\n\n" +
                        "This can happen when testing on the same computer.\n" +
                        "Close the other client's audio first, or test on separate computers."))
                elif "-9999" in error_msg or "Unanticipated host error" in error_msg:
                    self.master.after(0, lambda: messagebox.showerror("Audio Error", 
                        "Audio device initialization failed.\n\n" +
                        "Solutions:\n" +
                        "1. Grant Microphone permission in System Preferences\n" +
                        "2. Close other apps using microphone/speakers\n" +
                        "3. Try restarting the client\n" +
                        "4. Check if headphones/mic are properly connected"))
                else:
                    self.master.after(0, lambda e=e: messagebox.showerror("Error", f"Audio error: {e}"))
        else:
            # Stop audio streaming
            self.audio_streaming = False
            
            # Wait a moment for threads to notice the flag
            time.sleep(0.3)
            
            # Update button in main thread
            self.master.after(0, lambda: self.audio_btn.config(text="Start Audio"))
            
            # Safely close streams in a separate thread to avoid blocking
            threading.Thread(target=self._close_audio_streams, daemon=True).start()
            
            print(f"🎤 Audio stopping for {self.username}...")
    
    def _close_audio_streams(self):
        """Safely close audio streams without blocking"""
        try:
            if self.audio_input_stream:
                try:
                    self.audio_input_stream.stop_stream()
                    self.audio_input_stream.close()
                except Exception as e:
                    print(f"Input stream close error: {e}")
                self.audio_input_stream = None
        except Exception as e:
            print(f"Error closing input: {e}")
        
        try:
            if self.audio_output_stream:
                try:
                    self.audio_output_stream.stop_stream()
                    self.audio_output_stream.close()
                except Exception as e:
                    print(f"Output stream close error: {e}")
                self.audio_output_stream = None
        except Exception as e:
            print(f"Error closing output: {e}")
    
    def stream_audio(self):
        """Stream audio to server"""
        packet_count = 0
        while self.audio_streaming and self.running:
            try:
                if not self.audio_input_stream:
                    break
                    
                data = self.audio_input_stream.read(2048, exception_on_overflow=False)
                
                # Create packet: type(2) + username_len + username + audio_data
                username_bytes = self.username.encode('utf-8')
                packet = bytes([2, len(username_bytes)]) + username_bytes + data
                
                # Send via UDP (using stored port, not GUI widget)
                self.udp_socket.sendto(packet, (self.server_ip, self.server_udp_port))
                
                packet_count += 1
                # Log every 50 packets to confirm sending
                if packet_count % 50 == 0:
                    print(f"🎙️ Sent {packet_count} audio packets")
                    
            except OSError as e:
                # Stream was closed, exit gracefully
                print(f"Audio stream closed: {e}")
                break
            except Exception as e:
                print(f"Audio stream error: {e}")
                break
        
        print(f"🎤 Audio streaming thread ended for {self.username} (sent {packet_count} packets)")
    
    def toggle_presenting(self):
        """Toggle screen sharing"""
        if not self.presenting:
            self.send_message({'type': 'start_presenting'})
            self.presenting = True
            self.present_btn.config(text="Stop Presenting")
            threading.Thread(target=self.stream_screen, daemon=True).start()
        else:
            self.send_message({'type': 'stop_presenting'})
            self.presenting = False
            self.present_btn.config(text="Start Presenting")
    
    def stream_screen(self):
        """Stream screen to server"""
        print(f"📺 Starting screen share for {self.username}")
        frame_count = 0
        
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                
                while self.presenting and self.running:
                    try:
                        # Capture screen
                        screenshot = sct.grab(monitor)
                        img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                        
                        # Resize
                        img.thumbnail((800, 600), Image.LANCZOS)
                        
                        # Convert to base64
                        buffer = io.BytesIO()
                        img.save(buffer, format='JPEG', quality=60)
                        img_str = base64.b64encode(buffer.getvalue()).decode()
                        
                        # Send to server
                        self.send_message({
                            'type': 'screen_frame',
                            'frame': img_str
                        })
                        
                        frame_count += 1
                        if frame_count % 30 == 0:  # Log every 30 frames
                            print(f"📺 Sent {frame_count} screen frames")
                        
                        time.sleep(0.1)  # 10 FPS for screen sharing
                    except Exception as e:
                        print(f"Screen share frame error: {e}")
                        time.sleep(0.5)  # Wait before retry
                        
        except Exception as e:
            print(f"Screen share fatal error: {e}")
        finally:
            print(f"📺 Screen share stopped for {self.username}")
    
    def send_chat(self):
        """Send chat message"""
        message = self.chat_entry.get().strip()
        if message:
            self.send_message({
                'type': 'chat',
                'message': message
            })
            self.chat_entry.delete(0, tk.END)
    
    def display_chat_message(self, msg):
        """Display chat message"""
        self.chat_display.config(state=tk.NORMAL)
        timestamp = msg.get('timestamp', '')
        username = msg.get('username', '')
        message = msg.get('message', '')
        
        # Store in chat history (but skip system messages about users joining/leaving)
        if username not in ['System'] or 'joined' not in message:
            self.chat_history.append({
                'timestamp': timestamp,
                'username': username,
                'message': message
            })
        
        self.chat_display.insert(tk.END, f"[{timestamp}] {username}: {message}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def open_hf_dialog(self):
        """Open a chat dialog with the Personal Assistant."""
        dlg = tk.Toplevel(self.master)
        dlg.title("Personal Assistant")
        dlg.geometry("700x520")

        # Create main chat display
        chat_frame = ttk.Frame(dlg)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Chat history display
        self.assistant_chat = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, height=20)
        self.assistant_chat.pack(fill=tk.BOTH, expand=True)
        self.assistant_chat.config(state=tk.DISABLED)
        
        # Bottom frame for input and buttons
        bottom_frame = ttk.Frame(dlg)
        bottom_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        # Input field
        input_frame = ttk.Frame(bottom_frame)
        input_frame.pack(fill=tk.X, pady=(8, 0))
        
        message_entry = ttk.Entry(input_frame)
        message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        def send_message(event=None):
            prompt = message_entry.get().strip()
            if not prompt:
                return
            
            # Clear input
            message_entry.delete(0, tk.END)
            
            # Show user message
            self.assistant_chat.config(state=tk.NORMAL)
            ts = datetime.now().strftime('%H:%M:%S')
            self.assistant_chat.insert(tk.END, f"\n[{ts}] You: {prompt}\n")
            self.assistant_chat.see(tk.END)
            self.assistant_chat.config(state=tk.DISABLED)
            
            # Disable input while processing
            message_entry.config(state=tk.DISABLED)
            send_btn.config(state=tk.DISABLED)
            sum_btn.config(state=tk.DISABLED)
            
            def _get_response():
                try:
                    response = self.query_model(prompt)
                    ts = datetime.now().strftime('%H:%M:%S')
                    
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.NORMAL))
                    self.master.after(0, lambda: self.assistant_chat.insert(tk.END, f"[{ts}] Assistant: {response}\n"))
                    self.master.after(0, lambda: self.assistant_chat.see(tk.END))
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.DISABLED))
                except Exception as e:
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.NORMAL))
                    self.master.after(0, lambda: self.assistant_chat.insert(tk.END, f"\nError: {e}\n"))
                    self.master.after(0, lambda: self.assistant_chat.see(tk.END))
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.DISABLED))
                finally:
                    self.master.after(0, lambda: message_entry.config(state=tk.NORMAL))
                    self.master.after(0, lambda: send_btn.config(state=tk.NORMAL))
                    self.master.after(0, lambda: sum_btn.config(state=tk.NORMAL))
            
            threading.Thread(target=_get_response, daemon=True).start()

        # Send button
        send_btn = ttk.Button(input_frame, text="Send", command=send_message)
        send_btn.pack(side=tk.RIGHT)
        
        # Bind Enter key to send
        message_entry.bind('<Return>', send_message)

        # Button frame for additional controls
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        
        def summarize_chats():
            if not self.chat_history:
                self.assistant_chat.config(state=tk.NORMAL)
                self.assistant_chat.insert(tk.END, "\nNo chat history available yet.\n")
                self.assistant_chat.see(tk.END)
                self.assistant_chat.config(state=tk.DISABLED)
                return
                
            # Create a summarization prompt
            chat_text = "\n".join([
                f"[{chat['timestamp']}] {chat['username']}: {chat['message']}"
                for chat in self.chat_history
            ])
            summary_prompt = f"Please provide a summary of this group chat conversation, highlighting key discussions, questions asked, and important interactions between participants:\n\n{chat_text}"
            
            # Disable controls
            message_entry.config(state=tk.DISABLED)
            send_btn.config(state=tk.DISABLED)
            sum_btn.config(state=tk.DISABLED)
            
            def _summarize():
                try:
                    summary = self.query_model(summary_prompt)
                    ts = datetime.now().strftime('%H:%M:%S')
                    
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.NORMAL))
                    self.master.after(0, lambda: self.assistant_chat.insert(tk.END, f"\n[{ts}] Chat Summary:\n{summary}\n"))
                    self.master.after(0, lambda: self.assistant_chat.see(tk.END))
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.DISABLED))
                except Exception as e:
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.NORMAL))
                    self.master.after(0, lambda: self.assistant_chat.insert(tk.END, f"\nError generating summary: {e}\n"))
                    self.master.after(0, lambda: self.assistant_chat.see(tk.END))
                    self.master.after(0, lambda: self.assistant_chat.config(state=tk.DISABLED))
                finally:
                    self.master.after(0, lambda: message_entry.config(state=tk.NORMAL))
                    self.master.after(0, lambda: send_btn.config(state=tk.NORMAL))
                    self.master.after(0, lambda: sum_btn.config(state=tk.NORMAL))
            
            threading.Thread(target=_summarize, daemon=True).start()

        sum_btn = ttk.Button(btn_frame, text="Summarize Chats", command=summarize_chats)
        sum_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        close_btn = ttk.Button(btn_frame, text="Close", command=dlg.destroy)
        close_btn.pack(side=tk.RIGHT)

    def _hf_request_thread(self, prompt, result_widget, gen_btn):
        """Background thread that calls the HF API and updates UI widgets."""
        try:
            text = self.query_model(prompt)
            ts = datetime.now().strftime('%H:%M:%S')
            msg = {'username': 'Assistant', 'message': text, 'timestamp': ts}
            self.chat_history.append(msg)
            self.master.after(0, lambda: self.display_chat_message(msg))
        except Exception as e:
            err = f"Error calling HF API: {e}"
            self.master.after(0, lambda: result_widget.insert(tk.END, err + '\n'))
        finally:
            self.master.after(0, lambda: gen_btn.config(state=tk.NORMAL))
    
    def upload_file(self):
        """Upload file to server"""
        filepath = filedialog.askopenfilename()
        if filepath:
            try:
                filename = os.path.basename(filepath)
                with open(filepath, 'rb') as f:
                    filedata = base64.b64encode(f.read()).decode()
                
                filesize = os.path.getsize(filepath)
                
                self.send_message({
                    'type': 'file_upload',
                    'filename': filename,
                    'filesize': filesize,
                    'filedata': filedata
                })
                
                messagebox.showinfo("Success", f"File '{filename}' uploaded successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Upload failed: {e}")
    
    def download_file(self):
        """Download selected file"""
        selection = self.files_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a file to download")
            return
        
        filename = self.files_listbox.get(selection[0])
        
        # Request file from server
        self.send_message({
            'type': 'file_download',
            'filename': filename
        })
    
    def receive_tcp_messages(self):
        """Receive and process TCP messages from server"""
        while self.running and self.connected:
            try:
                msg = self.recv_message()
                if not msg:
                    if self.running:  # Only print if we didn't intentionally close
                        print("Disconnected from server")
                    break
                
                self.process_tcp_message(msg)
            except OSError as e:
                # Socket was closed (expected during shutdown)
                if self.running:
                    print(f"Connection closed: {e}")
                break
            except Exception as e:
                if self.running:
                    print(f"TCP receive error: {e}")
                break
        
        # Mark as disconnected
        self.connected = False
    
    def process_tcp_message(self, msg):
        """Process received TCP messages"""
        msg_type = msg.get('type')
        
        if msg_type == 'chat':
            self.display_chat_message(msg)
        
        elif msg_type == 'user_joined':
            self.users = msg['users']
            self.master.after(0, self.update_users_list)
            self.display_chat_message({
                'username': 'System',
                'message': f"{msg['username']} joined the session",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
        
        elif msg_type == 'user_left':
            self.users = msg['users']
            self.master.after(0, self.update_users_list)
            self.display_chat_message({
                'username': 'System',
                'message': f"{msg['username']} left the session",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            
            # Remove their video frame
            if msg['username'] in self.video_frames:
                del self.video_frames[msg['username']]
            
            # Clear presenter if they left
            if self.presenter == msg['username']:
                self.presenter = None
                self.master.after(0, lambda: self.screen_label.config(text="No presentation active", image=''))
        
        elif msg_type == 'presenter_changed':
            self.presenter = msg['presenter']
            if self.presenter:
                self.master.after(0, lambda: self.screen_label.config(text=f"{self.presenter} is presenting..."))
                if self.presenter == self.username:
                    self.master.after(0, lambda: self.present_btn.config(text="Stop Presenting", state=tk.NORMAL))
                else:
                    self.master.after(0, lambda: self.present_btn.config(text="Start Presenting", state=tk.DISABLED))
            else:
                self.master.after(0, lambda: self.screen_label.config(text="No presentation active", image=''))
                self.master.after(0, lambda: self.present_btn.config(text="Start Presenting", state=tk.NORMAL))
        
        elif msg_type == 'screen_frame':
            if msg['presenter'] == self.presenter and msg['presenter'] != self.username:
                # Display screen frame
                try:
                    img_data = base64.b64decode(msg['frame'])
                    img = Image.open(io.BytesIO(img_data))
                    
                    # Resize to fit display area
                    display_width = 800
                    display_height = 600
                    img.thumbnail((display_width, display_height), Image.LANCZOS)
                    
                    photo = ImageTk.PhotoImage(img)
                    # Update GUI in main thread
                    self.master.after(0, lambda p=photo: self._update_screen_display(p))
                except Exception as e:
                    print(f"Screen frame display error: {e}")
        
        elif msg_type == 'file_available':
            # Add file to listbox
            filename = msg['filename']
            if filename not in [self.files_listbox.get(i) for i in range(self.files_listbox.size())]:
                self.files_listbox.insert(tk.END, filename)
            
            self.display_chat_message({
                'username': 'System',
                'message': f"{msg['username']} shared file: {filename} ({msg['filesize']} bytes)",
                'timestamp': msg['timestamp']
            })
        
        elif msg_type == 'file_data':
            # Save downloaded file
            try:
                filename = msg['filename']
                filedata = base64.b64decode(msg['filedata'])
                
                # Ask user where to save
                save_path = filedialog.asksaveasfilename(initialfile=filename)
                if save_path:
                    with open(save_path, 'wb') as f:
                        f.write(filedata)
                    messagebox.showinfo("Success", f"File saved to {save_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Download failed: {e}")
    
    def receive_udp_streams(self):
        """Receive UDP video and audio streams"""
        while self.running and self.connected:
            try:
                data, addr = self.udp_socket.recvfrom(65535)
                
                if len(data) < 2:
                    continue
                
                stream_type = data[0]  # 1=video, 2=audio
                username_len = data[1]
                
                if len(data) < 2 + username_len:
                    continue
                
                username = data[2:2+username_len].decode('utf-8')
                payload = data[2+username_len:]
                
                if stream_type == 1:  # Video
                    # Decode video frame (in background thread is OK)
                    try:
                        nparr = np.frombuffer(payload, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            # Just store the frame, GUI will display it
                            self.video_frames[username] = frame.copy()
                    except Exception as e:
                        pass  # Silently skip bad frames
                
                elif stream_type == 2:  # Audio
                    # Play audio (can be done in background thread)
                    try:
                        if self.audio_output_stream and self.audio_streaming:
                            # Only play audio from others, not ourselves
                            if username != self.username:
                                # Log occasionally for debugging
                                if not hasattr(self, '_audio_packet_count'):
                                    self._audio_packet_count = {}
                                
                                if username not in self._audio_packet_count:
                                    self._audio_packet_count[username] = 0
                                
                                self._audio_packet_count[username] += 1
                                
                                # Log every 50 packets
                                if self._audio_packet_count[username] % 50 == 0:
                                    print(f"🔊 Received {self._audio_packet_count[username]} audio packets from {username}")
                                
                                self.audio_output_stream.write(payload, exception_on_underflow=False)
                    except Exception as e:
                        # Log audio playback errors occasionally
                        if not hasattr(self, '_audio_error_logged'):
                            self._audio_error_logged = True
                            print(f"⚠️ Audio playback error: {e}")
            
            except Exception as e:
                if self.running:
                    pass  # Silently handle UDP errors
    
    def update_users_list(self):
        """Update the users listbox"""
        self.users_listbox.delete(0, tk.END)
        for user in self.users:
            display_name = f"{user} (You)" if user == self.username else user
            self.users_listbox.insert(tk.END, display_name)
    
    def _update_screen_display(self, photo):
        """Update screen display in main thread"""
        try:
            self.screen_label.config(image=photo, text='')
            self.screen_label.image = photo  # Keep reference
        except:
            pass
    
    def update_video_grid(self):
        """Update video display grid - MUST run in main thread"""
        if not self.running or not self.connected:
            return
        
        try:
            # Clear existing video labels
            for widget in self.video_container.winfo_children():
                widget.destroy()
            
            # Create grid for video frames
            num_videos = len(self.video_frames)
            if num_videos == 0:
                label = tk.Label(self.video_container, text="No active video streams", 
                               anchor=tk.CENTER, bg='gray20', fg='white')
                label.pack(expand=True, fill=tk.BOTH)
                self.master.after(200, self.update_video_grid)
                return
            
            # Calculate grid dimensions
            cols = min(3, num_videos)
            rows = (num_videos + cols - 1) // cols
            
            for i, (username, frame) in enumerate(list(self.video_frames.items())):
                row = i // cols
                col = i % cols
                
                try:
                    # Create frame container
                    video_frame = tk.Frame(self.video_container, relief=tk.SOLID, 
                                         borderwidth=2, bg='black')
                    video_frame.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
                    
                    # Username label
                    name_label = tk.Label(video_frame, text=username, bg='black', 
                                        fg='white', font=('Arial', 10, 'bold'))
                    name_label.pack(side=tk.TOP, pady=2)
                    
                    # Video display
                    # Convert BGR to RGB
                    frame_copy = frame.copy()
                    rgb_frame = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb_frame)
                    photo = ImageTk.PhotoImage(img)
                    
                    video_label = tk.Label(video_frame, image=photo, bg='black')
                    video_label.image = photo  # Keep reference
                    video_label.pack(expand=True, fill=tk.BOTH)
                    
                except Exception as e:
                    # Silently skip this frame, will try again in next update
                    pass
            
            # Configure grid weights for responsive layout
            for i in range(cols):
                self.video_container.grid_columnconfigure(i, weight=1)
            for i in range(rows):
                self.video_container.grid_rowconfigure(i, weight=1)
            
        except Exception as e:
            # Silently handle errors
            pass
        
        # Schedule next update
        self.master.after(200, self.update_video_grid)
    
    def on_closing(self):
        """Handle window close event"""
        if self.connected:
            self.video_streaming = False
            self.audio_streaming = False
            self.presenting = False
            self.running = False
            
            # Wait a moment for threads to stop
            time.sleep(0.3)
            
            # Use safe audio stream closing
            self._close_audio_streams()
            
            # Use safe camera closing
            self._close_camera()
            
            # Close sockets
            if self.tcp_socket:
                try:
                    self.tcp_socket.close()
                except:
                    pass
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except:
                    pass
        else:
            self.running = False
        
        try:
            self.master.destroy()
        except:
            pass
if __name__ == "__main__":
    import tkinter as tk
    root = tk.Tk()
    client_app = LANClient(root)
    root.mainloop()
