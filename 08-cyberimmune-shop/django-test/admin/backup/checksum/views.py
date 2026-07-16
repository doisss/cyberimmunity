import hashlib
from django.http import JsonResponse
from django.conf import settings

def db_checksum(request):
    db = settings.BASE_DIR / "db.sqlite3"

    with open(db, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    return JsonResponse({"checksum": file_hash})
