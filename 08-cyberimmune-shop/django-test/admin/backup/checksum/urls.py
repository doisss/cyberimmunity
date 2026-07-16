from django.urls import path
from .views import db_checksum

urlpatterns = [
    path("", db_checksum, name="db_checksum")
]
