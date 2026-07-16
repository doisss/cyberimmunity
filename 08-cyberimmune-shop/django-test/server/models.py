# orders/models.py
from django.db import models
from cryptography.fernet import Fernet
import os
from django.conf import settings
from base64 import b64encode, b64decode
import orders

def f_encrypt(value: str) -> bytes:
    f = Fernet(settings.FERNET_KEY.encode())
    return f.encrypt(value.encode())

def f_decrypt(token: bytes) -> str:
    f = Fernet(settings.FERNET_KEY.encode())
    return f.decrypt(token).decode()

class EncryptedTextField(models.BinaryField):
    description = "Encrypted text storage"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return f_decrypt(value)
        except Exception:
            return value

    def get_prep_value(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            return f_encrypt(value)
        return value

class Order(models.Model):
    customer_name = models.CharField(max_length=200)
    address = EncryptedTextField()
    email = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} for {self.customer_name}"
