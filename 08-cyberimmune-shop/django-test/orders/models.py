# orders/models.py
from django.db import models

class Order(models.Model):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    item = models.CharField(max_length=255)
    quantity = models.IntegerField()

    def __str__(self):
        return f"{self.name} — {self.item} x {self.quantity}"
