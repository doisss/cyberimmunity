from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # маршруты заказов
    path("orders/", include("orders.urls")),

    # маршруты проверки чексуммы
    path("admin/checksum/", include("admin.backup.checksum.urls")),

    # маршруты выдачи БД и лога
    path("admin/download/", include("admin.backup.download.urls")),

    # стандартная Django админка
    path("admin/", admin.site.urls),

    # модуль админ-панели 
    path("control/", include("adminpanel.urls")),

]
