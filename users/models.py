from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    IS_PASSENGER = 'passenger'
    IS_DRIVER = 'driver'
    IS_ADMIN = 'admin'
    
    ROLE_CHOICES = [
        (IS_PASSENGER, 'Passenger'),
        (IS_DRIVER, 'Driver'),
        (IS_ADMIN, 'Admin'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=IS_PASSENGER)

    def __str__(self):
        return f"{self.username} ({self.role})"
