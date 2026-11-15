from django.urls import path

from . import views

app_name = "merchants"

urlpatterns = [
    path("switch/", views.SwitchMerchantView.as_view(), name="switch"),
]
