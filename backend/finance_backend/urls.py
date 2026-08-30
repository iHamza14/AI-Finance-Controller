from django.contrib import admin
from django.urls import path, include
from api.views import DashboardView

urlpatterns = [
    path('', DashboardView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]
