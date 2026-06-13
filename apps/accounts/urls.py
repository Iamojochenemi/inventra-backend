from django.urls import path
from .views import RegisterView, TestProtectedView


urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("protected/", TestProtectedView.as_view(), name="protected"),
]