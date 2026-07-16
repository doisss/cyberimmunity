# orders/views.py
from django.http import JsonResponse, FileResponse, HttpResponseForbidden
from django.contrib.admin.views.decorators import staff_member_required
import os
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from .forms import OrderForm
from .models import Order
from utils.audit_log import log_event
import logging
from validator.validators import validate_order_data, ValidationError

BACKUP_DIR = os.path.join(settings.BASE_DIR, "backups")

@staff_member_required
def get_latest_checksum(request):
    # возвращает содержание файла .sha256 для последнего бекапа
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".enc")])
    if not files:
        return JsonResponse({"error": "no backups"}, status=404)
    latest = files[-1]
    checksum_file = os.path.join(BACKUP_DIR, f"{latest}.sha256")
    if not os.path.exists(checksum_file):
        return JsonResponse({"error": "checksum missing"}, status=500)
    with open(checksum_file, "r") as f:
        checksum = f.read().strip()
    return JsonResponse({"backup": latest, "checksum": checksum})

@staff_member_required
def download_backup(request):
    # ожидаем, что клиент предварительно запросил checksum и подтвердил его
    # можно ожидать параметр ?ack=true
    if request.GET.get("ack") != "true":
        return JsonResponse({"error": "ack required"}, status=400)
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".enc")])
    if not files:
        return JsonResponse({"error": "no backups"}, status=404)
    latest = files[-1]
    path = os.path.join(BACKUP_DIR, latest)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=latest)

def create_order(request):
    if request.method == "POST":
        form = OrderForm(request.POST)
        audit = logging.getLogger('audit')

        if form.is_valid():

            # ------------------------------------
            # 1) Валидируем входящие данные (dict)
            # ------------------------------------
            try:
                validate_order_data(request.POST)  # ⚡ Главное исправление!
            except ValidationError as e:
                audit.error(f"Ошибка валидации: {str(e)} — данные: {request.POST}")

                return render(request, "orders/order_form.html", {
                    "error": str(e),
                    "form": form
                })

            # ------------------------------------
            # 2) Данные валидны — создаём заказ
            # ------------------------------------
            order = Order.objects.create(
                name=form.cleaned_data['name'],
                address=form.cleaned_data['address'],
                item=form.cleaned_data['item'],
                quantity=form.cleaned_data['quantity']
            )

            # Запись в secure_audit.log
            audit.info(
                f"Создан заказ ID={order.id}; "
                f"Имя={order.name}; "
                f"Товар={order.item}; "
                f"Кол-во={order.quantity}"
            )

            # Запись в основной журнал
            log_event(f"Order created: {order.id}")

            return render(request, "orders/success.html", {"order": order})

        # Ошибка django-формы
        log_event("Order validation failed (Django form)")
        return render(request, "orders/order_form.html", {"form": form})

    # GET запрос — показать форму
    return render(request, "orders/order_form.html", {"form": OrderForm()})


def order_form(request):
    return render(request, "orders/order_form.html")