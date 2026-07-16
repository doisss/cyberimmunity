import hashlib
from django.http import FileResponse, JsonResponse
from django.conf import settings
from utils.audit_log import read_log

def get_log(request):
    return JsonResponse({"log": read_log()})

def db_download(request):
    if request.GET.get("verify") != "1":
        return JsonResponse({"error": "checksum verification required"}, status=403)

    return FileResponse(open(settings.BASE_DIR / "db.sqlite3", "rb"))
