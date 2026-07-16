import socket
import logging
import argparse
import threading
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from colorama import init, Fore, Style

init(autoreset=True)

# === Global State ===
active_users = {}
user_pubkeys = {}
users_lock = threading.Lock()

# === Server RSA keys ===
srv_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
srv_public_key = srv_private_key.public_key()
srv_public_pem = srv_public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# ------------------------------------------------------
# FIRST: Encryption helper
# ------------------------------------------------------
def encrypt_payload(target_key, text):
    """Encrypt text using recipient public key."""
    max_len = 190
    encoded = text.encode("utf-8")

    if len(encoded) > max_len:
        raise ValueError("Message too long for RSA block")

    try:
        return target_key.encrypt(
            encoded,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
    except Exception as exc:
        logging.error(f"encrypt_payload error: {exc}")
        raise

# ------------------------------------------------------
# SECOND: Decryption helper
# ------------------------------------------------------
def decrypt_payload(encrypted_block):
    """Decrypt data using server private key."""
    try:
        cleartext = srv_private_key.decrypt(
            encrypted_block,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return cleartext.decode("utf-8")
    except Exception as exc:
        logging.error(f"decrypt_payload error: {exc}")
        raise

# ------------------------------------------------------
# Logging config
# ------------------------------------------------------
def init_logging(level_string, log_filename):
    lvl = getattr(logging, level_string.upper(), None)
    if not isinstance(lvl, int):
        raise ValueError("Invalid log level")

    logging.basicConfig(
        level=lvl,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        handlers=[logging.FileHandler(log_filename, encoding="utf-8"),
                  logging.StreamHandler()]
    )

# ------------------------------------------------------
# Client Thread
# ------------------------------------------------------
class UserThread(threading.Thread):
    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self.username = None
        self.user_key = None

    # ========= MAIN THREAD LOOP =========
    def run(self):
        global active_users, user_pubkeys

        # === Key exchange ===
        try:
            self.sock.send(srv_public_pem)
            raw_client_key = self.sock.recv(4096)
            self.user_key = serialization.load_pem_public_key(raw_client_key)
        except Exception as exc:
            logging.info(f"Key exchange failed: {exc}")
            self.sock.close()
            return

        # === Username negotiation ===
        while True:
            try:
                ask_name = encrypt_payload(self.user_key, "Enter your username: ")
                self.sock.send(ask_name)

                enc_name = self.sock.recv(1024)
                username_try = decrypt_payload(enc_name).strip()

                with users_lock:
                    if not username_try or username_try in active_users:
                        msg = encrypt_payload(self.user_key,
                                              "This username is taken or invalid. Try another.")
                        self.sock.send(msg)
                        continue

                    if len(active_users) >= 5:
                        too_many = encrypt_payload(
                            self.user_key, "Server supports up to 5 clients. Disconnecting."
                        )
                        self.sock.send(too_many)
                        self.sock.close()
                        return

                    self.username = username_try
                    active_users[self.username] = self.sock
                    user_pubkeys[self.username] = self.user_key

                    ok = encrypt_payload(self.user_key, "Username registered successfully.")
                    self.sock.send(ok)
                    break

            except Exception as exc:
                logging.info(f"Username error: {exc}")
                self.sock.close()
                return

        # === Message loop ===
        try:
            while True:
                encrypted_msg = self.sock.recv(4096)
                if not encrypted_msg:
                    break

                msg = decrypt_payload(encrypted_msg)

                # ================= Commands =================
                if msg == "/userlist":
                    with users_lock:
                        listing = "\n".join([f"\t{i+1}) {u}" for i, u in enumerate(active_users.keys())])
                    try:
                        reply = encrypt_payload(self.user_key, f"Connected users:\n{listing}")
                        self.sock.send(reply)
                    except ValueError:
                        err = encrypt_payload(self.user_key, "Userlist too long to send.")
                        self.sock.send(err)
                    continue

                if msg == "/help":
                    help_text = (
                        "Commands: /help, /exit, /clear, /userlist, "
                        "/dm [user] [msg], /changeuser [name], /backup, /load"
                    )
                    try:
                        reply = encrypt_payload(self.user_key, help_text)
                        self.sock.send(reply)
                    except ValueError:
                        err = encrypt_payload(self.user_key, "Help message too long.")
                        self.sock.send(err)
                    continue

                if msg.startswith("/changeuser "):
                    _, new_name = msg.split(maxsplit=1)
                    with users_lock:
                        if new_name in active_users:
                            err = encrypt_payload(self.user_key,
                                                  "Username already taken. Choose a different one.")
                            self.sock.send(err)
                        else:
                            del active_users[self.username]
                            del user_pubkeys[self.username]

                            self.username = new_name
                            active_users[new_name] = self.sock
                            user_pubkeys[new_name] = self.user_key

                            ok = encrypt_payload(self.user_key, f"Username changed to {new_name}.")
                            self.sock.send(ok)
                    continue

                if msg.startswith("/dm "):
                    parts = msg.split()
                    if len(parts) < 3:
                        err = encrypt_payload(self.user_key, "Usage: /dm recipient message")
                        self.sock.send(err)
                        continue

                    _, recipient, *payload_parts = parts
                    text_dm = " ".join(payload_parts)

                    with users_lock:
                        if recipient not in active_users:
                            err = encrypt_payload(self.user_key, "Recipient not found.")
                            self.sock.send(err)
                            continue

                        rec_key = user_pubkeys[recipient]

                        try:
                            enc_to_rec = encrypt_payload(rec_key, f"[DM from {self.username}] {text_dm}")
                            enc_me = encrypt_payload(self.user_key, f"[DM to {recipient}] {text_dm}")

                            active_users[recipient].send(enc_to_rec)
                            self.sock.send(enc_me)

                            logging.info(f"DM from {self.username} to {recipient}: {text_dm}")
                        except ValueError:
                            err = encrypt_payload(self.user_key, "Direct message too long.")
                            self.sock.send(err)
                    continue

                if msg == "/clear":
                    cmd = encrypt_payload(self.user_key, "/clear")
                    self.sock.send(cmd)
                    continue

                if not msg or msg == "/exit":
                    logging.info(f"Exit command from {self.username}")
                    break

                # ================= Normal chat =================
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                composed = f"[{timestamp}] {self.username}: {msg}"

                with users_lock:
                    for usr, sock_obj in active_users.items():
                        usr_key = user_pubkeys[usr]
                        try:
                            encrypted_out = encrypt_payload(usr_key, composed)
                            sock_obj.send(encrypted_out)
                        except ValueError:
                            err = encrypt_payload(usr_key, "Message too long.")
                            sock_obj.send(err)

        except Exception as exc:
            logging.info(f"Processing error: {exc}")

        # === Cleanup ===
        with users_lock:
            if self.username in active_users:
                del active_users[self.username]
                del user_pubkeys[self.username]
        self.sock.close()


# ------------------------------------------------------
# Server start
# ------------------------------------------------------
def run_server(bind_ip, bind_port):
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind((bind_ip, bind_port))
        ip, port = srv.getsockname()
        srv.listen(5)

        print("Server is running.")
        print(f"{Fore.YELLOW}Host: {Style.RESET_ALL}{ip}:{port}")
        logging.info(f"Server started on {ip}:{port}")

        while True:
            sock, addr = srv.accept()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] Connection from {addr}")
            logging.info(f"Accepted connection from {addr}")

            thr = UserThread(sock)
            thr.start()

    except KeyboardInterrupt:
        print("Server shutdown.")
        logging.info("Server stopped by KeyboardInterrupt")
    except OSError as exc:
        print("Server error:", exc)
        logging.error(f"Startup error: {exc}")


# ------------------------------------------------------
# MAIN
# ------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Secure Chat Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=12345)
    parser.add_argument("--loglevel", default="INFO")
    parser.add_argument("--logfile", default="server.log")

    options = parser.parse_args()

    init_logging(options.loglevel, options.logfile)
    run_server(options.host, options.port)
