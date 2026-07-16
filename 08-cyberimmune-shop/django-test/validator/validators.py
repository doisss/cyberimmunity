import re

class ValidationError(Exception):
    pass


def validate_name(name: str):
    if not name or len(name) < 2:
        raise ValidationError("Имя слишком короткое")

    if not re.match(r"^[A-Za-zА-Яа-яЁё\s\-]+$", name):
        raise ValidationError("Имя содержит недопустимые символы")


def validate_address(address: str):
    if len(address) < 5:
        raise ValidationError("Адрес слишком короткий")


def validate_item(item: str):
    if len(item) == 0:
        raise ValidationError("Товар не указан")


def validate_quantity(q):
    try:
        q = int(q)
    except:
        raise ValidationError("Количество должно быть числом")

    if q <= 0:
        raise ValidationError("Количество должно быть > 0")

    if q > 1000:
        raise ValidationError("Количество слишком большое")

    return q


def validate_order_data(data: dict):
    validate_name(data.get("name"))
    validate_address(data.get("address"))
    validate_item(data.get("item"))
    validate_quantity(data.get("quantity"))
