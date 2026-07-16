import os
from django.conf import settings
from django.http import HttpResponse, FileResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from orders.models import Order

# Главная панель администратора нашего модуля
@staff_member_required
def dashboard(request):
    return render(request, "adminpanel/dashboard.html")


# Выдача информации из БД (список заказов)
@staff_member_required
def orders_list(request):
    orders = Order.objects.all().order_by("-id")
    return render(request, "adminpanel/orders_list.html", {"orders": orders})


# Выдача журнала событий
@staff_member_required
def download_logs(request):
    log_file_path = os.path.join(settings.BASE_DIR, "secure_audit.log")

    if not os.path.exists(log_file_path):
        return HttpResponse("Файл лога ещё не создан.", status=404)

    return FileResponse(open(log_file_path, "rb"), as_attachment=True, filename="secure_audit.log")
