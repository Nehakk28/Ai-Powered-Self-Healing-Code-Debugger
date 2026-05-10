# your_app/middleware.py
from django.http import HttpResponse
from datetime import datetime

class DateCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.cutoff_date = datetime(2026, 8, 31)  

    def __call__(self, request):
        if datetime.now() > self.cutoff_date:
            return HttpResponse("")
        
        response = self.get_response(request)
        return response