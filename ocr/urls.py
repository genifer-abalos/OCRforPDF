"""OCRforCBM URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
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
from . import views

urlpatterns = [
    path('', views.upload, name='upload'),
    # path('upload/', views.upload, name='upload'),
    path('data-sg/', views.submit_sg_data),
    path('data-cs/', views.submit_cs_data),
    path('data-tca/', views.submit_tca_data),
    path('data-lubecheck/', views.submit_lubecheck_data),
    path('submit-sg/', views.submit_sg_data),
    path('submit-cs/', views.submit_cs_data),
    path('submit-tca/', views.submit_tca_data),
    path('submit-lubecheck/', views.submit_lubecheck_data),
]
