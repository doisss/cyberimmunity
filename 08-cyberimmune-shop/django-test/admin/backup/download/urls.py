from django.urls import path
from .views import db_download

urlpatterns = [
    path("", db_download, name="db_download")
]
