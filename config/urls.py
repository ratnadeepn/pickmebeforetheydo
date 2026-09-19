from django.contrib import admin
from django.urls import path, include

import accounts

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    # path('accounts/', include("accounts.urls", namespace="accounts")),
    path('api/', include("task.urls", namespace="tasks")),
]
