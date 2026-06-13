from rest_framework import generics
from .serializers import RegisterSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsAdminOrVendor, IsAdminOrVendor, IsVendor


class TestProtectedView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrVendor]

    def get(self, request):
        return Response({
            "message": "Vendor access granted",
            "user": request.user.email,
            "role": request.user.role
        })