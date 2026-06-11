"""
URL configuration for backend_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.norm_admin.site.urls if hasattr(admin.site, 'norm_admin') else admin.site.urls),
    path('api/', include('companies.urls')),
    path('api/v1/auth/', include('companies.urls')),  # Compatibility for desktop app
    path('api/billing/', include('billing.urls')),
    path('api/erp/', include('erp_core.urls')),
    path('api/v1/', include('erp_core.urls')), # Match frontend API_VERSION 'v1' for sync (api/v1/sync/pull/)
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
