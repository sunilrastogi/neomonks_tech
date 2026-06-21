"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from apps.accounts.urls import api_urlpatterns as accounts_api
from apps.accounts.urls import page_urlpatterns as accounts_pages

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/workflow/', include('apps.workflow.api.urls')),
    path('api/v1/realtime/', include('apps.realtime.urls')),
    path('api/v1/auth/', include((accounts_api, 'accounts'))),
    *accounts_pages,
] + staticfiles_urlpatterns()
