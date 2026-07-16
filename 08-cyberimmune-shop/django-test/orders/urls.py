from django.urls import path
from .views import create_order, order_form

urlpatterns = [
    path("", order_form),           
    path("new/", create_order),
]
