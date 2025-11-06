#!/usr/bin/env python3
"""
LAN Multi-User Communication Server
Handles video, audio, screen sharing, chat, and file transfer
"""

import socket
import threading
import struct
import json
import time
import os
from datetime import datetime

class LANServer:
    def __init__(self, host='0.0.0.0', tcp_port=5555, udp_port=5556):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        
        # Client management
        self.clients = {}  # {username: {'tcp': socket, 'address': (ip, port), 'udp_port': port}}
        self.clients_lock = threading.Lock()
        
        # Session state
        self.presenter = None
        self.chat_history = []
        self.files = {}  # {filename: file_data}
        
        # Sockets
        self.tcp_socket = None
        self.udp_socket = None
        
        # Running flag
        self.running = False
        
        print(f"[SERVER] Initializing server on {host}:{tcp_port} (TCP) and {udp_port} (UDP)")
    
    def start(self):
        """Start the server"""
        self.running = True
        
        # Setup TCP socket for control, chat, and file transfer
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind((self.host, self.tcp_port))
        self.tcp_socket.listen(10)
        
        # Setup UDP socket for video and audio streaming
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.host, self.udp_port))
        
        print(f"[SERVER] TCP listening on {self.host}:{self.tcp_port}")
        print(f"[SERVER] UDP listening on {self.host}:{self.udp_port}")
        
        # Start UDP handler thread
        udp_thread = threading.Thread(target=self.handle_udp_streams, daemon=True)
        udp_thread.start()
        
        # Accept TCP connections
        try:
            while self.running:
                try:
                    self.tcp_socket.settimeout(1.0)
                    client_sock, addr = self.tcp_socket.accept()
                    print(f"[SERVER] New connection from {addr}")
                    threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")
        finally:
            self.shutdown()
    
    def handle_client(self, client_sock, addr):
        """Handle individual client TCP connection"""
        username = None
        try:
            # Receive initial registration
            data = self.recv_message(client_sock)
            if data and data['type'] == 'register':
                username = data['username']
                udp_port = data['udp_port']
                
                with self.clients_lock:
                    self.clients[username] = {
                        'tcp': client_sock,
                        'address': addr,
                        'udp_port': udp_port
                    }
                
                print(f"[SERVER] {username} registered from {addr}")
                
                # Send current state
                self.send_message(client_sock, {
                    'type': 'registered',
                    'users': list(self.clients.keys()),
                    'chat_history': self.chat_history,
                    'presenter': self.presenter
                })
                
                # Notify others
                self.broadcast_tcp({
                    'type': 'user_joined',
                    'username': username,
                    'users': list(self.clients.keys())
                }, exclude=username)
                
                # Handle messages from this client
                while self.running:
                    msg = self.recv_message(client_sock)
                    if not msg:
                        break
                    
                    self.process_message(username, msg)
            
        except Exception as e:
            print(f"[SERVER] Error with {username or addr}: {e}")
        finally:
            if username:
                self.disconnect_client(username)
    
    def process_message(self, username, msg):
        """Process different message types"""
        msg_type = msg.get('type')
        
        if msg_type == 'chat':
            # Broadcast chat message
            chat_msg = {
                'type': 'chat',
                'username': username,
                'message': msg['message'],
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            self.chat_history.append(chat_msg)
            self.broadcast_tcp(chat_msg)
            
        elif msg_type == 'start_presenting':
            # Set presenter
            if self.presenter is None:
                self.presenter = username
                self.broadcast_tcp({
                    'type': 'presenter_changed',
                    'presenter': username
                })
                print(f"[SERVER] {username} started presenting")
            
        elif msg_type == 'stop_presenting':
            # Stop presenting
            if self.presenter == username:
                self.presenter = None
                self.broadcast_tcp({
                    'type': 'presenter_changed',
                    'presenter': None
                })
                print(f"[SERVER] {username} stopped presenting")
        
        elif msg_type == 'screen_frame':
            # Broadcast screen frame to all except sender
            frame_msg = {
                'type': 'screen_frame',
                'presenter': username,
                'frame': msg['frame']
            }
            self.broadcast_tcp(frame_msg, exclude=username)
        
        elif msg_type == 'file_upload':
            # Handle file upload
            filename = msg['filename']
            filesize = msg['filesize']
            filedata = msg['filedata']
            
            self.files[filename] = filedata
            
            # Notify all clients about new file
            self.broadcast_tcp({
                'type': 'file_available',
                'username': username,
                'filename': filename,
                'filesize': filesize,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            print(f"[SERVER] File '{filename}' uploaded by {username} ({filesize} bytes)")
        
        elif msg_type == 'file_download':
            # Send file to requesting client
            filename = msg['filename']
            if filename in self.files:
                with self.clients_lock:
                    if username in self.clients:
                        self.send_message(self.clients[username]['tcp'], {
                            'type': 'file_data',
                            'filename': filename,
                            'filedata': self.files[filename]
                        })
    
    def handle_udp_streams(self):
        """Handle UDP video and audio streams"""
        print("[SERVER] UDP stream handler started")
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(65535)
                
                # Parse header: type (1 byte) + username length (1 byte) + username
                if len(data) < 2:
                    continue
                
                stream_type = data[0]  # 1=video, 2=audio
                username_len = data[1]
                
                if len(data) < 2 + username_len:
                    continue
                
                username = data[2:2+username_len].decode('utf-8')
                payload = data[2+username_len:]
                
                # Broadcast to all other clients
                with self.clients_lock:
                    for user, info in self.clients.items():
                        if user != username:
                            try:
                                # Send to client's UDP port
                                client_addr = (info['address'][0], info['udp_port'])
                                self.udp_socket.sendto(data, client_addr)
                            except Exception as e:
                                pass
                                
            except Exception as e:
                if self.running:
                    print(f"[SERVER] UDP error: {e}")
    
    def broadcast_tcp(self, message, exclude=None):
        """Broadcast TCP message to all clients"""
        with self.clients_lock:
            for username, info in list(self.clients.items()):
                if username != exclude:
                    try:
                        self.send_message(info['tcp'], message)
                    except:
                        pass
    
    def disconnect_client(self, username):
        """Handle client disconnection"""
        with self.clients_lock:
            if username in self.clients:
                try:
                    self.clients[username]['tcp'].close()
                except:
                    pass
                del self.clients[username]
                
                # Clear presenter if disconnected
                if self.presenter == username:
                    self.presenter = None
                
                print(f"[SERVER] {username} disconnected")
                
                # Notify others
                self.broadcast_tcp({
                    'type': 'user_left',
                    'username': username,
                    'users': list(self.clients.keys()),
                    'presenter': self.presenter
                })
    
    def send_message(self, sock, msg):
        """Send length-prefixed JSON message"""
        data = json.dumps(msg).encode('utf-8')
        sock.sendall(struct.pack('>I', len(data)) + data)
    
    def recv_message(self, sock):
        """Receive length-prefixed JSON message"""
        try:
            # Read message length
            raw_msglen = self.recvall(sock, 4)
            if not raw_msglen:
                return None
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            # Read message data
            data = self.recvall(sock, msglen)
            if not data:
                return None
            
            return json.loads(data.decode('utf-8'))
        except:
            return None
    
    def recvall(self, sock, n):
        """Helper to receive n bytes"""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)
    
    def shutdown(self):
        """Shutdown server"""
        self.running = False
        
        # Close all client connections
        with self.clients_lock:
            for username, info in self.clients.items():
                try:
                    info['tcp'].close()
                except:
                    pass
        
        # Close server sockets
        if self.tcp_socket:
            self.tcp_socket.close()
        if self.udp_socket:
            self.udp_socket.close()
        
        print("[SERVER] Server shutdown complete")

if __name__ == "__main__":
    import sys
    
    # Get host IP
    host = '0.0.0.0'  # Listen on all interfaces
    tcp_port = 5555
    udp_port = 5556
    
    if len(sys.argv) > 1:
        tcp_port = int(sys.argv[1])
    if len(sys.argv) > 2:
        udp_port = int(sys.argv[2])
    
    # Display server IP
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n{'='*50}")
    print(f"LAN Communication Server")
    print(f"{'='*50}")
    print(f"Server IP: {local_ip}")
    print(f"TCP Port: {tcp_port}")
    print(f"UDP Port: {udp_port}")
    print(f"{'='*50}\n")
    print("Clients should connect to this IP address")
    print("Press Ctrl+C to stop the server\n")
    
    server = LANServer(host=host, tcp_port=tcp_port, udp_port=udp_port)
    server.start()