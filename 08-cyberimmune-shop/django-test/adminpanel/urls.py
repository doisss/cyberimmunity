from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name="admin_dashboard"),
    path('orders/', views.orders_list, name="admin_orders_list"),
    path('logs/', views.download_logs, name="admin_download_logs"),
]
