from django.urls import path

from . import views

app_name = "stores"

urlpatterns = [
    path("<slug:slug>/", views.public_store_detail, name="public_detail"),
]
