
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, TextChoices
from django.db.models import EmailField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .managers import UserManager
from django.db import models

class User(AbstractUser):
    """
    Default custom user model for AI_DEBUGGER.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """
    class UserType(TextChoices):
        ADMIN = "ADMIN", "Admin"
        customer = "Customer", "customer"

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    user_type = CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.customer,
    )
    
    block_reason = models.TextField(blank=True, null=True, help_text="Reason for blocking the user")

    objects: ClassVar[UserManager] = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid




class ChatSession(models.Model):
    """Store chat sessions for coding assistant"""
    
    # Unique identifier
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_sessions'
    )
    
    # Session metadata
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    # Session status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-last_updated']
        indexes = [
            models.Index(fields=['user', '-last_updated']),
            models.Index(fields=['session_id']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.title[:50]}"
    
    @classmethod
    def create_session(cls, user, title=None):
        """Create a new chat session"""
        session_id = str(uuid.uuid4())[:8]
        return cls.objects.create(
            session_id=session_id,
            user=user,
            title=title or "New Chat"
        )


class ChatMessage(models.Model):
    """Store individual messages in a chat session"""
    
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    
    # Relationships
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    # Message data
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    raw_content = models.TextField(blank=True, null=True)  # Store unformatted content
    
    # Metadata
    timestamp = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Optional: Track tokens/cost
    token_count = models.IntegerField(null=True, blank=True)
    
    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class CodeSnippet(models.Model):
    """Store code snippets from chat sessions (optional)"""
    
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='code_snippets'
    )
    
    language = models.CharField(max_length=50, default='python')
    code = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.language} - {self.code[:50]}"


class PasswordResetToken(models.Model):
    """Store tokens for password reset functionality"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Reset token for {self.user.email}"
