
import os
import socket
import argparse
import threading
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend

class EncryptedChatClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client_socket = None
        self.username = None
        self.message_lock = threading.Lock()
        self.history = []
        self.load_or_generate_keys()
        self.server_public_key = None

    def generate_and_save_keys(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        with open('private_key.pem', 'wb') as f:
            f.write(self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open('public_key.pem', 'wb') as f:
            f.write(self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        print("New RSA keypair generated and saved.")

    def load_or_generate_keys(self):
        private_key_file = 'private_key.pem'
        public_key_file = 'public_key.pem'
        if os.path.exists(private_key_file) and os.path.exists(public_key_file):
            try:
                with open(private_key_file, 'rb') as f:
                    self.private_key = serialization.load_pem_private_key(
                        f.read(),
                        password=None,
                        backend=default_backend()
                    )
                with open(public_key_file, 'rb') as f:
                    self.public_key = serialization.load_pem_public_key(
                        f.read(),
                        backend=default_backend()
                    )
                print("Existing RSA keys loaded.")
            except Exception as e:
                print(f"Key load error: {e}. Generating new keys.")
                self.generate_and_save_keys()
        else:
            self.generate_and_save_keys()

        self.public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def encrypt_data(self, public_key, data):
        max_length = 190
        if len(data.encode('utf-8')) > max_length:
            raise ValueError(f"Message too long ({len(data.encode('utf-8'))} bytes). Max {max_length}.")
        return public_key.encrypt(
            data.encode('utf-8'),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def decrypt_data(self, encrypted_data):
        return self.private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        ).decode('utf-8')

    def load_backup(self):
        try:
            with open('chat_backup.enc', 'rb') as f:
                file_content = f.read()
                if len(file_content) < 256:
                    raise ValueError("Backup file corrupted or too small.")
                encrypted_key = file_content[:256]
                encrypted_data = file_content[256:]
            fernet_key = self.private_key.decrypt(
                encrypted_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            cipher = Fernet(fernet_key)
            decrypted = cipher.decrypt(encrypted_data).decode('utf-8')
            self.history = decrypted.split('\n') if decrypted else []
            for msg in self.history:
                if msg:
                    print(msg)
            print("Backup loaded successfully.")
        except FileNotFoundError:
            print("Backup file not found.")
        except ValueError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Failed to load backup: {e}")

    def save_backup(self):
        try:
            data = '\n'.join(self.history)
            fernet_key = Fernet.generate_key()
            cipher = Fernet(fernet_key)
            encrypted_data = cipher.encrypt(data.encode('utf-8'))
            encrypted_key = self.public_key.encrypt(
                fernet_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            with open('chat_backup.enc', 'wb') as f:
                f.write(encrypted_key + encrypted_data)
            print("Chat backup saved and encrypted.")
        except Exception as e:
            print(f"Failed to save backup: {e}")

    def connect(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            server_public_pem = self.client_socket.recv(4096)
            self.server_public_key = serialization.load_pem_public_key(server_public_pem)
            self.client_socket.send(self.public_pem)
            return True
        except Exception as e:
            print(f"Connect error: {e}")
            return False

    def get_username(self):
        try:
            encrypted_username_prompt = self.client_socket.recv(4096)
            username_prompt = self.decrypt_data(encrypted_username_prompt)
            username = input(username_prompt)
            encrypted_username = self.encrypt_data(self.server_public_key, username)
            self.client_socket.send(encrypted_username)
            encrypted_response = self.client_socket.recv(4096)
            response = self.decrypt_data(encrypted_response)
            if "Please" in response or "supports up to" in response:
                print(response)
                return False
            self.username = username
            print("Help: /help  /backup  /load  /userlist  /dm [user] [msg]  /exit")
            return True
        except Exception as e:
            print(f"Username error: {e}")
            return False

    def listen_to_server(self):
        while True:
            try:
                encrypted_data = self.client_socket.recv(8192)
                if not encrypted_data:
                    break
                decrypted_data = self.decrypt_data(encrypted_data)
                if decrypted_data == "/clear":
                    os.system('cls' if os.name == 'nt' else 'clear')
                    continue
                # print received message and re-print input prompt
                with self.message_lock:
                    print("\n" + decrypted_data)
                    # keep history
                    self.history.append(decrypted_data)
                    print(f"{self.username}> ", end='', flush=True)
            except Exception as e:
                print(f"Listener error: {e}")
                break

    def send_messages(self):
        while True:
            try:
                print(f"{self.username}> ", end='', flush=True)
                message = input()
                if not message:
                    continue
                if message == "/backup":
                    self.save_backup()
                    continue
                if message == "/load":
                    self.load_backup()
                    continue
                encrypted_message = self.encrypt_data(self.server_public_key, message)
                self.client_socket.send(encrypted_message)
                if message == "/exit":
                    self.save_backup()
                    break
            except ValueError as e:
                print(f"Error: {e}")
                continue
            except KeyboardInterrupt:
                print("\nClosing connection...")
                try:
                    encrypted_exit = self.encrypt_data(self.server_public_key, "/exit")
                    self.client_socket.send(encrypted_exit)
                    self.save_backup()
                except Exception:
                    pass
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                break

    def run(self):
        if self.connect():
            if self.get_username():
                listener = threading.Thread(target=self.listen_to_server, daemon=True)
                listener.start()
                self.send_messages()
        if self.client_socket:
            self.client_socket.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect to secure chat server.")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP")
    parser.add_argument("--port", type=int, default=12345, help="Server port")
    args = parser.parse_args()

    client = EncryptedChatClient(args.host, args.port)
    client.run()
