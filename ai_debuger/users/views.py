from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView
from django.views import View
from django.contrib.auth import authenticate, login, get_user_model
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponseRedirect
import re
import smtplib
import uuid
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

User = get_user_model()
from django.db import transaction
from django.utils import timezone

class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None):
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


class SettingsView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name", "email"]
    template_name = "users/settings.html"
    success_message = _("Settings successfully updated")

    def get_object(self, queryset: QuerySet | None = None):
        return self.request.user

    def get_success_url(self):
        return reverse("users:settings")


user_update_view = UserUpdateView.as_view()
settings_view = SettingsView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:detail", kwargs={"pk": self.request.user.pk})


user_redirect_view = UserRedirectView.as_view()


class LoginView(View):
    template_name = "auth/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return HttpResponseRedirect("/dashboard/")
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        print("your email",email)
        print("your password",password)
        # Validate inputs
        if not email or not password:
            messages.error(request, "Email and password are required")
            return render(request, self.template_name)

        # Check for blocked user before authentication
        is_admin = False
        try:
            user_obj = User.objects.get(email=email)

            print("user_obj",user_obj.user_type)
            if user_obj.check_password(password):
                is_admin = user_obj.user_type.upper() == "ADMIN"
                # Check directly against string "ADMIN" or iterate properly if needed
                # Based on models.py: ADMIN = "ADMIN", "Admin"
                if user_obj.user_type.upper() != "ADMIN" and not user_obj.is_active:
                     reason = user_obj.block_reason or "No reason provided."
                     messages.error(request, f"Your account is blocked. Reason: {reason}")
                     return render(request, self.template_name)
        except User.DoesNotExist:
            # Continue to standard auth to handle invalid credentials generically
            pass

        # Use authenticate instead of manual check
        # This automatically handles the backend
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Successfully logged in!")
            
            if is_admin:
                return HttpResponseRedirect("/admin-dashboard/")
               
            else:
                 return HttpResponseRedirect("/dashboard/")
        else:
            messages.error(request, "Invalid email or password")
            return render(request, self.template_name)


login_view = LoginView.as_view()


class SignupView(View):
    template_name = "auth/signup.html"

    def get(self, request):
        # Redirect if user is already logged in
        if request.user.is_authenticated:
            return HttpResponseRedirect("/dashboard/")
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        # 1️⃣ Basic validation - check for empty fields
        if not all([email, password, confirm_password]):
            messages.error(request, "All fields are required")
            return render(request, self.template_name)

        # 2️⃣ Validate email format
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address")
            return render(request, self.template_name)

        # 3️⃣ Check password match
        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return render(request, self.template_name)

        # 4️⃣ Validate password strength
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long")
            return render(request, self.template_name)

        # 5️⃣ Check email uniqueness
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return render(request, self.template_name)

        # 7️⃣ Create user with error handling
        try:
            user = User.objects.create_user(
                email=email,
                password=password
            )

            # 8️⃣ Auto login after signup
            # Use authenticate to get the backend automatically set
            authenticated_user = authenticate(request, username=email, password=password)
            
            if authenticated_user is not None:
                login(request, authenticated_user)
                messages.success(request, "Account created successfully!")
                return HttpResponseRedirect("/dashboard/")
            else:
                messages.error(request, "Account created but login failed. Please try logging in.")
                return redirect("/")  # redirect to login

        except IntegrityError:
            messages.error(request, "An error occurred. Please try again.")
            return render(request, self.template_name)
        except Exception as e:
            print(f"Signup error: {str(e)}")
            messages.error(request, "An unexpected error occurred. Please try again.")
            return render(request, self.template_name)


sign_up_view = SignupView.as_view()

from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.db.models import Count, Avg, Q, Sum
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils import timezone
from datetime import timedelta
import json
from django.db.models.functions import ExtractHour
from .models import ChatSession, ChatMessage, CodeSnippet
class DashboardView(LoginRequiredMixin, View):
    """Main dashboard with statistics and charts"""
    
    def get(self, request):
        user = request.user
        
        # Date ranges
        today = timezone.now().date()
        week_ago = timezone.now() - timedelta(days=7)
        month_ago = timezone.now() - timedelta(days=30)
        
        # ============ OVERVIEW STATISTICS ============
        total_chats = ChatSession.objects.filter(user=user, is_active=True).count()
        
        total_messages = ChatMessage.objects.filter(
            session__user=user,
            session__is_active=True
        ).count()
        
        total_code_snippets = CodeSnippet.objects.filter(
            message__session__user=user,
            message__session__is_active=True
        ).count()
        
        # Chats this week
        chats_this_week = ChatSession.objects.filter(
            user=user,
            is_active=True,
            created_at__gte=week_ago
        ).count()
        
        # Calculate growth percentage
        chats_last_week = ChatSession.objects.filter(
            user=user,
            is_active=True,
            created_at__gte=week_ago - timedelta(days=7),
            created_at__lt=week_ago
        ).count()
        
        if chats_last_week > 0:
            growth_percentage = ((chats_this_week - chats_last_week) / chats_last_week) * 100
        else:
            growth_percentage = 100 if chats_this_week > 0 else 0
        
        # Average messages per chat
        avg_messages = ChatMessage.objects.filter(
            session__user=user,
            session__is_active=True
        ).values('session').annotate(
            msg_count=Count('id')
        ).aggregate(Avg('msg_count'))['msg_count__avg'] or 0
        
        # ============ ACTIVITY CHART DATA (Last 7 Days) ============
        activity_data = []
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            count = ChatSession.objects.filter(
                user=user,
                is_active=True,
                created_at__date=date
            ).count()
            activity_data.append({
                'date': date.strftime('%b %d'),
                'count': count
            })
        
        # ============ LANGUAGE DISTRIBUTION ============
        # Since we don't have language field in model, we'll simulate it
        # You can add a language field to ChatSession model later
        language_distribution = [
            {'language': 'Python', 'count': int(total_chats * 0.4), 'color': '#3776ab'},
            {'language': 'JavaScript', 'count': int(total_chats * 0.25), 'color': '#f7df1e'},
            {'language': 'C++', 'count': int(total_chats * 0.15), 'color': '#00599c'},
            {'language': 'Rust', 'count': int(total_chats * 0.12), 'color': '#dea584'},
            {'language': 'Go', 'count': int(total_chats * 0.08), 'color': '#00add8'},
        ]
        
        # ============ RECENT ACTIVITY ============
        recent_chats = ChatSession.objects.filter(
            user=user,
            is_active=True
        ).order_by('-last_updated')[:5]
        
        # ============ SUCCESS RATE ============
        # Simulate success rate (you can add a status field to track this)
        success_rate = 87.5  # Example percentage
        
        # ============ MONTHLY TREND ============
        monthly_data = []
        for i in range(5, -1, -1):
            month_start = (today.replace(day=1) - timedelta(days=i*30))
            month_name = month_start.strftime('%b')
            
            count = ChatSession.objects.filter(
                user=user,
                is_active=True,
                created_at__month=month_start.month,
                created_at__year=month_start.year
            ).count()
            
            monthly_data.append({
                'month': month_name,
                'count': count
            })
        
        # ============ PEAK USAGE HOURS ============
        hours_data = (
            ChatMessage.objects
            .filter(
                session__user=user,
                session__is_active=True
            )
            .annotate(hour=ExtractHour('timestamp'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('hour')
        )
                
        # Format hours data
        peak_hours = []
        for hour in range(24):
            count = next((item['count'] for item in hours_data if item['hour'] == hour), 0)
            peak_hours.append({
                'hour': f"{hour:02d}:00",
                'count': count
            })
        
        # Get top 5 peak hours
        peak_hours_sorted = sorted(peak_hours, key=lambda x: x['count'], reverse=True)[:5]
        
        context = {
            # Overview stats
            'total_chats': total_chats,
            'total_messages': total_messages,
            'total_code_snippets': total_code_snippets,
            'chats_this_week': chats_this_week,
            'growth_percentage': round(growth_percentage, 1),
            'avg_messages': round(avg_messages, 1),
            'success_rate': success_rate,
            
            # Chart data
            'activity_data': json.dumps(activity_data),
            'language_distribution': json.dumps(language_distribution),
            'monthly_data': json.dumps(monthly_data),
            'peak_hours': json.dumps(peak_hours),
            'peak_hours_top': peak_hours_sorted,
            
            # Recent activity
            'recent_chats': recent_chats,
        }
        
        print(f"\n📊 DASHBOARD:")
        print(f"   User: {user.email}")
        print(f"   Total Chats: {total_chats}")
        print(f"   Total Messages: {total_messages}")
        print(f"   This Week: {chats_this_week}")
        print(f"   Growth: {growth_percentage:.1f}%\n")
        
        return render(request, 'users/dashboard.html', context)


# Export view
dashboard_view = DashboardView.as_view()




from django.views import View
from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin


import re
from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db import transaction


class Debugger(LoginRequiredMixin, View):
    template_name = "users/debugger.html"
    
    def get(self, request):
        """Display the debugger editor"""
        return render(request, self.template_name)
    
    def post(self, request):
        """Handle code analysis submission"""
        code = request.POST.get("code", "").strip()
        
        # Clean up syntax highlighting artifacts (aggressive cleanup)
        code = re.sub(r'(<span [^>]*>|class="syntax-[^"]+">|</span>)', '', code, flags=re.IGNORECASE)
        
        language = request.POST.get("language", "python")
        
        # Validate code input
        if not code:
            messages.error(request, "Please enter some code to debug")
            return render(request, self.template_name)
        
        try:
            # TODO: Replace with your actual AI debugging logic
            analysis = {
                "code": code,
                "language": language,
                "issues": [
                    {
                        "line": 10,
                        "type": "error",
                        "severity": "high",
                        "message": "Undefined variable detected",
                        "suggestion": "Define the variable before using it"
                    }
                ],
                "suggestions": [
                    "Add error handling for file operations",
                    "Consider using context managers"
                ],
                "security_issues": 1,
                "performance_issues": 0,
                "bugs_found": 3
            }
            
            context = {
                'analysis': analysis,
                'code': code,
                'language': language
            }
            
            messages.success(request, "Code analysis completed!")
            return render(request, self.template_name, context)
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return render(request, self.template_name, {'code': code})


class DebuggerFeedbackView(LoginRequiredMixin, View):
    """Handle feedback from debugger analysis"""
    
    def post(self, request):
        from ai_debuger.users.models import ChatSession, ChatMessage
        
        feedback = request.POST.get('feedback')  # 'good' or 'bad'
        code = request.POST.get('code', '')
        analysis_text = request.POST.get('analysis_text', '')
        
        print(f"\n🔔 FEEDBACK RECEIVED: {feedback}")
        print(f"   Code length: {len(code)}")
        print(f"   Analysis length: {len(analysis_text)}")
        
        if feedback == 'good':
            # User is happy - just thank them
            messages.success(request, "🎉 Thanks for your feedback!")
            return redirect('users:debugger_answer_view')
        
        elif feedback == 'bad':
            # User needs help - redirect to Coding Assistant
            try:
                # Create new chat session
                chat_session = ChatSession.create_session(
                    user=request.user,
                    title="Debug Help from Debugger"
                )
                
                # Create initial message with code and analysis
                initial_message = f"""I need help with this code. The debugger analyzed it but I need more assistance.

**Code:**
```python
{code}
```

**Analysis:**
{analysis_text}

Can you help me fix the issues?"""
                
                # Save message
                ChatMessage.objects.create(
                    session=chat_session,
                    role='user',
                    content=initial_message,
                    raw_content=initial_message,
                    timestamp=timezone.now()
                )
                
                print(f"✅ Created chat session: {chat_session.session_id}")
                
                messages.info(request, "💬 Opening Coding Assistant...")
                return redirect(f'/coding-assistant/?chat_id={chat_session.session_id}')
                
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                messages.error(request, f"Error: {str(e)}")
                return redirect('users:debugger_answer_view')
        
        return redirect('users:debugger_answer_view')


# Add at bottom:


# View instances
debugger_view = Debugger.as_view()
debugger_feedback_view = DebuggerFeedbackView.as_view()



# UPDATED VIEWS.PY - WITH FIXED CHAT FUNCTIONALITY
from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
import re
import html


def clean_code_thoroughly(code):
    """Clean HTML artifacts from code"""
    if not code:
        return code
    code = html.unescape(code)
    code = re.sub(r'<[^>]+>', '', code)
    code = re.sub(r'\s*class\s*=\s*["\'][^"\']*["\']', '', code, flags=re.IGNORECASE)
    code = re.sub(r'\s*style\s*=\s*["\'][^"\']*["\']', '', code, flags=re.IGNORECASE)
    return code.strip()


class DebuggerAnswer(View):
    """Fixed debugger with proper session handling"""
    template_name = "users/debugger_answer.html"
    
    def get(self, request):
        """Display the debugger editor"""
        # Get chat history from session (or initialize empty)
        chat_history = request.session.get('chat_history', [])
        current_code = request.session.get('current_code', '')
        
        context = {
            'chat_history': chat_history,
            'code': current_code
        }


        print(context)
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Handle all interactions"""
        from ai_debuger.utility.ai_client import EnhancedAIClient
        
        # Get and clean code
        raw_code = request.POST.get("code", "").strip()
        code = clean_code_thoroughly(raw_code)
        
        language = request.POST.get("language", "python")
        chat_mode = request.POST.get("chat_mode", "false") == "true"
        message = request.POST.get("message", "").strip()
        
        # Initialize AI client
        ai_client = EnhancedAIClient()
        
        # CRITICAL FIX: Get existing chat history from session FIRST
        chat_history = request.session.get('chat_history', [])
        
        print(f"\n{'='*60}")
        print(f"📥 POST REQUEST:")
        print(f"   chat_mode: {chat_mode}")
        print(f"   message: '{message}'")
        print(f"   code_length: {len(code)}")
        print(f"   existing_chat_history: {len(chat_history)} messages")
        print(f"{'='*60}\n")
        
        # ROUTE 1: Analyze Code Button
        if not chat_mode:
            r =  self._handle_analyze_button(request, code, language, ai_client, chat_history)
            print("the r", r)
            return r
        
        # ROUTE 2: Chat Message
        if chat_mode and message:

            c =  self._handle_chat_message(request, code, language, message, ai_client, chat_history)
            print("the c",c)
            return c
        
        # Fallback
        print("⚠️ WARNING: Reached fallback - no action taken")
        return render(request, self.template_name, {
            'chat_history': chat_history,
            'code': code,
            'language': language
        })
    # In your DebuggerAnswer view, FIND the _handle_analyze_button method
    # UPDATE it to mark the AI response as an analysis message:

    def _handle_analyze_button(self, request, code, language, ai_client, chat_history):
        """Handle Analyze Code button"""
        try:
            print("🔍 Analyzing code...")
            
            # Call AI for analysis
            analysis_result = ai_client.analyze_code(code, language)

            print(analysis_result)
            
            # Add USER message
            chat_history.append({
                'type': 'user',
                'message': f'Please analyze this  code and return ther correct code ',
                'timestamp': timezone.now().strftime('%I:%M %p')
            })
            
            # Format the analysis as a message string
            ai_message = self._format_analysis_message(analysis_result)
            
            # Add AI response with formatted message
            chat_history.append({
                'type': 'ai',
                'message': ai_message,
                'timestamp': timezone.now().strftime('%I:%M %p'),
                'analysis_data': analysis_result
            })
            
            # Save to session
            request.session['chat_history'] = chat_history
            request.session['current_code'] = code  # ← Save original code
            
            print("code", code)
            print("analysis_result",analysis_result)
            # ⚠️ KEY FIX: Pass BOTH the original code AND analysis
            return render(request, self.template_name, {
                'chat_history': chat_history,
                'code': code,  # ← This puts original code in the textarea
                'analysis': analysis_result,  # ← This is for the JavaScript
                'language': language
            })
            
        except Exception as e:
            print(f"❌ Error: {e}")
            messages.error(request, f"Error: {str(e)}")
            return render(request, self.template_name, {
                'chat_history': chat_history,
                'code': code
            })

    def _format_analysis_message(self, analysis):
        """Format analysis dict into a chat message string"""
        bugs_found = analysis.get('bugs_found', 0)
        explanation = analysis.get('explanation', '')
        
        if bugs_found > 0:
            return f"✅ Analysis Complete!\n\nI found {bugs_found} issue(s).\n\n{explanation}\n\n✨ I've updated the code in the editor!"
        else:
            return f"✅ Analysis Complete!\n\n{explanation}"


# Also update _handle_chat_message to NOT have is_analysis flag:

    def _handle_chat_message(self, request, code, language, message, ai_client, chat_history):
        """Handle chat message"""
        try:
            print(f"💬 Processing chat message: '{message}'")
            
            # Add user message
            chat_history.append({
                'type': 'user',
                'message': message,
                'timestamp': timezone.now().strftime('%I:%M %p')
            })
            
            # Get AI response
            ai_response = ai_client.chat(message, code, language)
            
            # Add AI response WITHOUT is_analysis flag
            chat_history.append({
                'type': 'ai',
                'message': ai_response,
                'timestamp': timezone.now().strftime('%I:%M %p'),
                'is_analysis': False  # ← Regular chat message
            })
            
            request.session['chat_history'] = chat_history
            request.session['current_code'] = code
            
            return render(request, self.template_name, {
                'chat_history': chat_history,
                'code': code
            })
            
        except Exception as e:
            print(f"❌ Error: {e}")
            messages.error(request, f"Error: {str(e)}")
            return render(request, self.template_name, {
                'chat_history': chat_history,
                'code': code
            })
    def _format_analysis_for_chat(self, analysis):
        """Format analysis results for chat"""
        bugs_found = analysis.get('bugs_found', 0)
        
        msg = f"✅ **Analysis Complete!**\n\n"
        
        if bugs_found == 0:
            msg += "🎉 Your code looks good!\n\n"
        else:
            msg += f"I found **{bugs_found}** issue{'s' if bugs_found != 1 else ''}.\n\n"
        
        if analysis.get('issues'):
            msg += "**🐛 Issues:**\n"
            for issue in analysis['issues'][:5]:
                severity_emoji = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢"
                }.get(issue.get('severity', 'low'), "🔵")
                msg += f"{severity_emoji} {issue.get('message', 'Unknown')}\n"
        
        if analysis.get('suggestions'):
            msg += "\n**💡 Suggestions:**\n"
            for sugg in analysis['suggestions'][:3]:
                msg += f"• {sugg}\n"
        
        if analysis.get('explanation'):
            msg += f"\n**📝 Summary:**\n{analysis['explanation']}\n"
        
        if analysis.get('corrected_code') and bugs_found > 0:
            msg += "\n✨ **I've updated the code!**"
        
        return msg


class ClearChatView(View):
    """Clear chat history"""
    def get(self, request):
        # Clear session data
        if 'chat_history' in request.session:
            del request.session['chat_history']
        if 'current_code' in request.session:
            del request.session['current_code']
        
        request.session.modified = True
        
        messages.success(request, "Chat cleared!")
        return redirect('users:debugger_answer_view')


# Exports
debugger_answer_view = DebuggerAnswer.as_view()
clear_chat_view = ClearChatView.as_view()





from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import datetime
import markdown
import uuid


class CodingAssistantView(LoginRequiredMixin, View):
    """ChatGPT-style Coding Assistant with Database Storage"""
    template_name = "users/coding_assistant.html"
    
    def get(self, request):
        """Display the chat interface"""
        from .models import ChatSession  # Adjust import
        
        # Get current chat ID from query params
        current_chat_id = request.GET.get('chat_id')
        
        # Get user's chat sessions from database
        user_sessions = ChatSession.objects.filter(
            user=request.user,
            is_active=True
        ).order_by('-last_updated')[:20]
        
        current_messages = []
        current_session = None
        
        if current_chat_id:
            # Load session from database
            try:
                current_session = ChatSession.objects.get(
                    session_id=current_chat_id,
                    user=request.user
                )
                # Get messages for this session
                current_messages = list(current_session.messages.all().values(
                    'role', 'content', 'timestamp'
                ))
                
                print(f"\n📖 GET Request (DB):")
                print(f"   Chat ID: {current_chat_id}")
                print(f"   Messages from DB: {len(current_messages)}")
                
            except ChatSession.DoesNotExist:
                messages.warning(request, "Chat session not found")
                current_chat_id = None
        
        # Format recent chats for sidebar
        recent_chats = [
            {
                'id': session.session_id,
                'title': session.title,
                'created_at': session.created_at,
                'last_updated': session.last_updated
            }
            for session in user_sessions
        ]
        
        print(f"   Total User Chats: {len(recent_chats)}\n")
        
        context = {
            'chat_messages': current_messages,
            'current_chat_id': current_chat_id,
            'recent_chats': recent_chats,
            'current_session': current_session
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Handle chat message and save to database"""
        from ai_debuger.utility.coding_ai_client import CodingAIClient
        from .models import ChatSession, ChatMessage  # Adjust import
        
        # Get message
        message = request.POST.get('message', '').strip()
        
        if not message:
            return redirect('users:coding_assistant')
        
        # Get current chat ID
        current_chat_id = request.GET.get('chat_id')
        
        print(f"\n{'='*60}")
        print(f"💬 POST REQUEST (DB)")
        print(f"   Chat ID: {current_chat_id}")
        print(f"   Message: {message[:100]}")
        
        # Get or create chat session
        if current_chat_id:
            try:
                chat_session = ChatSession.objects.get(
                    session_id=current_chat_id,
                    user=request.user
                )
                print(f"   Using existing session: {chat_session.title}")
            except ChatSession.DoesNotExist:
                # Create new session if not found
                chat_session = ChatSession.create_session(
                    user=request.user,
                    title=message[:50] + ('...' if len(message) > 50 else '')
                )
                current_chat_id = chat_session.session_id
                print(f"   Created new session: {current_chat_id}")
        else:
            # Create new session
            chat_session = ChatSession.create_session(
                user=request.user,
                title=message[:50] + ('...' if len(message) > 50 else '')
            )
            current_chat_id = chat_session.session_id
            print(f"   Created new session: {current_chat_id}")
        
        try:
            # Use transaction to ensure atomicity
            with transaction.atomic():
                # Save user message to database
                user_msg = ChatMessage.objects.create(
                    session=chat_session,
                    role='user',
                    content=message,
                    raw_content=message,
                    timestamp=timezone.now()
                )
                
                print(f"   ✅ User message saved (ID: {user_msg.id})")
                
                # Get chat history from database for AI context
                chat_history = list(
                    chat_session.messages.exclude(id=user_msg.id).values(
                        'role', 'content', 'timestamp'
                    )
                )
                
                print(f"   Chat History: {len(chat_history)} messages")
                
                # Get AI response
                ai_client = CodingAIClient()
                ai_response = ai_client.chat(message, history=chat_history)
                
                # Format response
                formatted_response = self._format_response(ai_response)
                
                print(f"   🤖 AI Response: {len(ai_response)} chars")
                
                # Save AI response to database
                ai_msg = ChatMessage.objects.create(
                    session=chat_session,
                    role='assistant',
                    content=formatted_response,
                    raw_content=ai_response,  # Store unformatted version
                    timestamp=timezone.now()
                )
                
                print(f"   ✅ AI message saved (ID: {ai_msg.id})")
                
                # Update session metadata
                chat_session.last_updated = timezone.now()
                chat_session.save(update_fields=['last_updated'])
                
                print(f"   ✅ Session updated")
                print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            # Save error message to database
            try:
                ChatMessage.objects.create(
                    session=chat_session,
                    role='assistant',
                    content=f"⚠️ Error: {str(e)}<br><br>Please check:<br>• Ollama is running<br>• Model is installed",
                    timestamp=timezone.now()
                )
            except:
                pass
            
            messages.error(request, f"Error: {str(e)}")
        
        # Redirect back to same chat
        return redirect(f"{request.path}?chat_id={current_chat_id}")
    
    def _format_response(self, text):
        """Format AI response with markdown"""
        try:
            html = markdown.markdown(
                text,
                extensions=['fenced_code', 'codehilite', 'nl2br']
            )
            return html
        except:
            return text.replace('\n', '<br>')


class NewChatView(LoginRequiredMixin, View):
    """Start a new chat session"""
    
    def get(self, request):
        from .models import ChatSession  # Adjust import
        
        # Create new session in database
        new_session = ChatSession.create_session(
            user=request.user,
            title="New Chat"
        )
        
        print(f"\n🆕 NEW CHAT (DB):")
        print(f"   Session ID: {new_session.session_id}")
        print(f"   User: {request.user.email}\n")
        
        messages.success(request, "Started new chat!")
        
        return redirect(f"/coding-assistant/?chat_id={new_session.session_id}")


class DeleteChatView(View):
    """Delete a specific chat session"""
    
    def post(self, request, session_id):
        from users.models import ChatSession  # Adjust import
        
        try:
            chat_session = ChatSession.objects.get(
                session_id=session_id,
               
            )
            
            # Soft delete
            chat_session.is_active = False
            chat_session.save(update_fields=['is_active'])
            
            # Or hard delete:
            # chat_session.delete()
            
            print(f"\n🗑️ DELETED CHAT:")
            print(f"   Session ID: {session_id}")
            print(f"   Title: {chat_session.title}\n")
            
            messages.success(request, "Chat deleted successfully!")
            
        except ChatSession.DoesNotExist:
            messages.error(request, "Chat not found")
        
        return redirect('users:coding_assistant')



class ClearAllChatsView(LoginRequiredMixin, View):
    """Clear ALL chat history for user"""
    
    def get(self, request):
        from your_app.models import ChatSession  # Adjust import
        
        # Count before clearing
        total_chats = ChatSession.objects.filter(
            user=request.user,
            is_active=True
        ).count()
        
        print(f"\n🗑️ CLEAR ALL CHATS (DB):")
        print(f"   User: {request.user.email}")
        print(f"   Deleting: {total_chats} chats\n")
        
        # Soft delete all user's chats
        ChatSession.objects.filter(
            user=request.user,
            is_active=True
        ).update(is_active=False)
        
        # Or hard delete:
        # ChatSession.objects.filter(user=request.user).delete()
        
        messages.success(request, f"Cleared {total_chats} chats!")
        return redirect('users:coding_assistant')


class ExportChatView(LoginRequiredMixin, View):
    """Export chat session as JSON or Markdown"""
    
    def get(self, request, session_id):
        from your_app.models import ChatSession  # Adjust import
        from django.http import JsonResponse, HttpResponse
        
        try:
            chat_session = ChatSession.objects.get(
                session_id=session_id,
                user=request.user
            )
            
            export_format = request.GET.get('format', 'json')
            
            if export_format == 'json':
                # Export as JSON
                messages = list(chat_session.messages.all().values(
                    'role', 'content', 'raw_content', 'timestamp'
                ))
                
                data = {
                    'session_id': chat_session.session_id,
                    'title': chat_session.title,
                    'created_at': chat_session.created_at.isoformat(),
                    'messages': messages
                }
                
                response = JsonResponse(data)
                response['Content-Disposition'] = f'attachment; filename="chat_{session_id}.json"'
                return response
            
            elif export_format == 'markdown':
                # Export as Markdown
                md_content = f"# {chat_session.title}\n\n"
                md_content += f"Created: {chat_session.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                md_content += "---\n\n"
                
                for msg in chat_session.messages.all():
                    role_label = "**You:**" if msg.role == 'user' else "**Assistant:**"
                    md_content += f"{role_label}\n\n{msg.raw_content or msg.content}\n\n---\n\n"
                
                response = HttpResponse(md_content, content_type='text/markdown')
                response['Content-Disposition'] = f'attachment; filename="chat_{session_id}.md"'
                return response
            
        except ChatSession.DoesNotExist:
            messages.error(request, "Chat not found")
            return redirect('users:coding_assistant')


# Export views
coding_assistant_view = CodingAssistantView.as_view()
new_chat_view = NewChatView.as_view()
delete_chat_view = DeleteChatView.as_view()
clear_all_chats_view = ClearAllChatsView.as_view()
export_chat_view = ExportChatView.as_view()




from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db.models import Count, Q
from .models import ChatSession, ChatMessage


class ChatListView(LoginRequiredMixin, View):
    """Display all chat sessions for the logged-in user"""
    
    def get(self, request):
        # Get filter parameters
        search_query = request.GET.get('search', '')
        language = request.GET.get('language', '')
        date_range = request.GET.get('date_range', '30')
        
        # Base queryset
        chats = ChatSession.objects.filter(
            user=request.user,
            is_active=True
        )
        
        # Apply search filter
        if search_query:
            chats = chats.filter(
                Q(title__icontains=search_query) |
                Q(messages__content__icontains=search_query)
            ).distinct()
        
        # Apply date filter
        from django.utils import timezone
        from datetime import timedelta
        
        if date_range == '1':
            today = timezone.now().date()
            chats = chats.filter(last_updated__date=today)
        elif date_range == '7':
            week_ago = timezone.now() - timedelta(days=7)
            chats = chats.filter(last_updated__gte=week_ago)
        elif date_range == '30':
            month_ago = timezone.now() - timedelta(days=30)
            chats = chats.filter(last_updated__gte=month_ago)
        
        # Annotate with message count
        chats = chats.annotate(
            message_count=Count('messages')
        )
        
        print(f"\n📋 CHAT LIST:")
        print(f"   User: {request.user.email}")
        print(f"   Total Chats: {chats.count()}")
        print(f"   Search: {search_query or 'None'}\n")
        
        context = {
            'chats': chats,
            'search_query': search_query,
            'language': language,
            'date_range': date_range,
        }
        
        return render(request, 'users/chat_list.html', context)


class ChatDetailView(LoginRequiredMixin, View):
    """Display detailed view of a specific chat session"""
    
    def get(self, request, session_id):
        chat = get_object_or_404(
            ChatSession,
            session_id=session_id,
        )
        
        messages_list = chat.messages.all().order_by('timestamp')
        
        print(f"\n👁️ CHAT DETAIL:")
        print(f"   Session ID: {session_id}")
        print(f"   Title: {chat.title}")
        print(f"   Messages: {messages_list.count()}\n")
        
        context = {
            'chat': chat,
            'messages': messages_list,
        }
        
        return render(request, 'users/chat_detail.html', context)


class NewChatView(LoginRequiredMixin, View):
    """Start a new chat session"""
    
    def get(self, request):
        # Create new session in database
        new_session = ChatSession.create_session(
            user=request.user,
            title="New Chat"
        )
        
        print(f"\n🆕 NEW CHAT (DB):")
        print(f"   Session ID: {new_session.session_id}")
        print(f"   User: {request.user.email}\n")
        
        messages.success(request, "Started new chat!")
        
        return redirect(f"/coding-assistant/?chat_id={new_session.session_id}")


class DeleteChatView(View):
    """Delete a specific chat session"""
    
    def post(self, request, session_id):
        try:
            chat_session = ChatSession.objects.get(
                session_id=session_id,
               
            )
            
            title = chat_session.title
            
            # Soft delete
            chat_session.is_active = False
            chat_session.save(update_fields=['is_active'])
            
            # Or hard delete (uncomment if you prefer):
            # chat_session.delete()
            
            print(f"\n🗑️ DELETED CHAT:")
            print(f"   Session ID: {session_id}")
            print(f"   Title: {title}\n")
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Chat deleted successfully!'
                })
            
            messages.success(request, "Chat deleted successfully!")
            return redirect('users:chat_list')
            
        except ChatSession.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': 'Chat not found'
                }, status=404)
            
            messages.error(request, "Chat not found")
            return redirect('users:chat_list')


class ClearAllChatsView(LoginRequiredMixin, View):
    """Clear ALL chat history for user"""
    
    def get(self, request):
        # Count before clearing
        total_chats = ChatSession.objects.filter(
            user=request.user,
            is_active=True
        ).count()
        
        print(f"\n🗑️ CLEAR ALL CHATS (DB):")
        print(f"   User: {request.user.email}")
        print(f"   Deleting: {total_chats} chats\n")
        
        # Soft delete all user's chats
        ChatSession.objects.filter(
            user=request.user,
            is_active=True
        ).update(is_active=False)
        
        # Or hard delete (uncomment if you prefer):
        # ChatSession.objects.filter(user=request.user).delete()
        
        messages.success(request, f"Cleared {total_chats} chats!")
        return redirect('users:coding_assistant')


class ExportChatView(LoginRequiredMixin, View):
    """Export chat session as JSON or Markdown"""
    
    def get(self, request, session_id):
        try:
            chat_session = ChatSession.objects.get(
                session_id=session_id,
                user=request.user
            )
            
            export_format = request.GET.get('format', 'json')
            
            if export_format == 'json':
                # Export as JSON
                messages_data = list(chat_session.messages.all().values(
                    'role', 'content', 'raw_content', 'timestamp'
                ))
                
                data = {
                    'session_id': chat_session.session_id,
                    'title': chat_session.title,
                    'created_at': chat_session.created_at.isoformat(),
                    'messages': messages_data
                }
                
                response = JsonResponse(data)
                response['Content-Disposition'] = f'attachment; filename="chat_{session_id}.json"'
                
                print(f"\n📥 EXPORT CHAT (JSON):")
                print(f"   Session ID: {session_id}")
                print(f"   Messages: {len(messages_data)}\n")
                
                return response
            
            elif export_format == 'markdown':
                # Export as Markdown
                md_content = f"# {chat_session.title}\n\n"
                md_content += f"Created: {chat_session.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                md_content += "---\n\n"
                
                for msg in chat_session.messages.all():
                    role_label = "**You:**" if msg.role == 'user' else "**Assistant:**"
                    md_content += f"{role_label}\n\n{msg.raw_content or msg.content}\n\n---\n\n"
                
                response = HttpResponse(md_content, content_type='text/markdown')
                response['Content-Disposition'] = f'attachment; filename="chat_{session_id}.md"'
                
                print(f"\n📥 EXPORT CHAT (MARKDOWN):")
                print(f"   Session ID: {session_id}\n")
                
                return response
            
        except ChatSession.DoesNotExist:
            messages.error(request, "Chat not found")
            return redirect('users:chat_list')


# Export views for use in urls.py
chat_list_view = ChatListView.as_view()
chat_detail_view = ChatDetailView.as_view()
new_chat_view = NewChatView.as_view()
delete_chat_view = DeleteChatView.as_view()
clear_all_chats_view = ClearAllChatsView.as_view()
export_chat_view = ExportChatView.as_view()

from django.urls import reverse_lazy

from django.contrib.auth.views import LogoutView

class UserLogoutView(LogoutView):
    next_page = reverse_lazy("users:login")


logout_view = UserLogoutView.as_view()

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.db.models import Count, Q, Avg, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import timedelta
from ai_debuger.users.models import User, ChatSession, ChatMessage, CodeSnippet
import json


class AdminDashboardView(LoginRequiredMixin, UserPassesTestMixin,TemplateView):
    """Admin dashboard with comprehensive analytics and visualizations"""
    template_name = 'users/admin_dashboard.html'
    
    def test_func(self):
        """Only allow admin users"""
        return self.request.user.user_type.upper() == User.UserType.ADMIN
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Date ranges
        today = timezone.now().date()
        last_7_days = today - timedelta(days=7)
        last_30_days = today - timedelta(days=30)
        last_90_days = today - timedelta(days=90)
        
        # ===== USER STATISTICS =====
        total_users = User.objects.count()
        admin_users = User.objects.filter(user_type='ADMIN').count()
        customer_users = User.objects.filter(user_type='Customer').count()
        
        # New users in different periods
        new_users_today = User.objects.filter(date_joined__date=today).count()
        new_users_7days = User.objects.filter(date_joined__date__gte=last_7_days).count()
        new_users_30days = User.objects.filter(date_joined__date__gte=last_30_days).count()
        
        # Active users (users with sessions in last 30 days)
        active_users_30days = User.objects.filter(
            chat_sessions__created_at__gte=last_30_days
        ).distinct().count()
        
        context['user_stats'] = {
            'total': total_users,
            'admins': admin_users,
            'customers': customer_users,
            'new_today': new_users_today,
            'new_7days': new_users_7days,
            'new_30days': new_users_30days,
            'active_30days': active_users_30days,
        }
        
        # ===== CHAT SESSION STATISTICS =====
        total_sessions = ChatSession.objects.count()
        active_sessions = ChatSession.objects.filter(is_active=True).count()
        sessions_today = ChatSession.objects.filter(created_at__date=today).count()
        sessions_7days = ChatSession.objects.filter(created_at__date__gte=last_7_days).count()
        sessions_30days = ChatSession.objects.filter(created_at__date__gte=last_30_days).count()
        
        # Average sessions per user
        avg_sessions_per_user = ChatSession.objects.values('user').annotate(
            session_count=Count('id')
        ).aggregate(avg=Avg('session_count'))['avg'] or 0
        
        context['session_stats'] = {
            'total': total_sessions,
            'active': active_sessions,
            'today': sessions_today,
            'last_7days': sessions_7days,
            'last_30days': sessions_30days,
            'avg_per_user': round(avg_sessions_per_user, 2),
        }
        
        # ===== MESSAGE STATISTICS =====
        total_messages = ChatMessage.objects.count()
        user_messages = ChatMessage.objects.filter(role='user').count()
        assistant_messages = ChatMessage.objects.filter(role='assistant').count()
        messages_today = ChatMessage.objects.filter(created_at__date=today).count()
        messages_7days = ChatMessage.objects.filter(created_at__date__gte=last_7_days).count()
        messages_30days = ChatMessage.objects.filter(created_at__date__gte=last_30_days).count()
        
        # Average messages per session
        avg_messages_per_session = ChatMessage.objects.values('session').annotate(
            msg_count=Count('id')
        ).aggregate(avg=Avg('msg_count'))['avg'] or 0
        
        # Total tokens (if tracked)
        total_tokens = ChatMessage.objects.aggregate(
            total=Sum('token_count')
        )['total'] or 0
        
        context['message_stats'] = {
            'total': total_messages,
            'user_messages': user_messages,
            'assistant_messages': assistant_messages,
            'today': messages_today,
            'last_7days': messages_7days,
            'last_30days': messages_30days,
            'avg_per_session': round(avg_messages_per_session, 2),
            'total_tokens': total_tokens,
        }
        
        # ===== CODE SNIPPET STATISTICS =====
        total_snippets = CodeSnippet.objects.count()
        snippets_by_language = CodeSnippet.objects.values('language').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        context['snippet_stats'] = {
            'total': total_snippets,
            'by_language': list(snippets_by_language),
        }
        
        # ===== CHART DATA =====
        
        # 1. User Growth Chart (Last 30 days)
        user_growth_data = User.objects.filter(
            date_joined__date__gte=last_30_days
        ).annotate(
            date=TruncDate('date_joined')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        context['user_growth_chart'] = json.dumps({
            'labels': [item['date'].strftime('%Y-%m-%d') for item in user_growth_data],
            'data': [item['count'] for item in user_growth_data],
        })
        
        # 2. Sessions Per Day Chart (Last 30 days)
        sessions_per_day = ChatSession.objects.filter(
            created_at__date__gte=last_30_days
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        context['sessions_chart'] = json.dumps({
            'labels': [item['date'].strftime('%Y-%m-%d') for item in sessions_per_day],
            'data': [item['count'] for item in sessions_per_day],
        })
        
        # 3. Messages Per Day Chart (Last 30 days)
        messages_per_day = ChatMessage.objects.filter(
            created_at__date__gte=last_30_days
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        context['messages_chart'] = json.dumps({
            'labels': [item['date'].strftime('%Y-%m-%d') for item in messages_per_day],
            'data': [item['count'] for item in messages_per_day],
        })
        
        # 4. User Type Distribution (Pie Chart)
        context['user_type_chart'] = json.dumps({
            'labels': ['Admin', 'Customer'],
            'data': [admin_users, customer_users],
        })
        
        # 5. Message Role Distribution (Pie Chart)
        context['message_role_chart'] = json.dumps({
            'labels': ['User Messages', 'Assistant Messages'],
            'data': [user_messages, assistant_messages],
        })
        
        # 6. Top 10 Most Active Users
        top_users = User.objects.annotate(
            session_count=Count('chat_sessions'),
            message_count=Count('chat_sessions__messages')
        ).order_by('-session_count')[:10]
        
        context['top_users'] = top_users
        
        # 7. Recent Activity (Last 10 sessions)
        recent_sessions = ChatSession.objects.select_related('user').order_by('-created_at')[:10]
        context['recent_sessions'] = recent_sessions
        
        # 8. Language Usage Distribution
        language_labels = [item['language'] for item in snippets_by_language]
        language_data = [item['count'] for item in snippets_by_language]
        
        context['language_chart'] = json.dumps({
            'labels': language_labels,
            'data': language_data,
        })
        
        # 9. Monthly Trends (Last 6 months)
        six_months_ago = today - timedelta(days=180)
        monthly_sessions = ChatSession.objects.filter(
            created_at__date__gte=six_months_ago
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        
        context['monthly_chart'] = json.dumps({
            'labels': [item['month'].strftime('%B %Y') for item in monthly_sessions],
            'data': [item['count'] for item in monthly_sessions],
        })
        print(context)
        
        return context


admin_dashboard_view = AdminDashboardView.as_view()



from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.views import View
from django.shortcuts import redirect
from django.contrib import messages
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from ai_debuger.users.models import User


class UserManagementView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """User management page for admins"""
    template_name = 'users/user_management.html'
    
    def test_func(self):
        """Only allow admin users"""
        print(f"<-----------------{self.request.user.user_type}------------------->")
        return self.request.user.user_type.upper() == User.UserType.ADMIN
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all users with their session and message counts
        users = User.objects.annotate(
            session_count=Count('chat_sessions'),
            message_count=Count('chat_sessions__messages')
        ).order_by('-date_joined')
        
        # Calculate stats
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)
        
        context['users'] = users
        context['total_users'] = users.count()
        context['active_users'] = users.filter(is_active=True).count()
        context['blocked_users'] = users.filter(is_active=False).count()
        context['new_users_30days'] = users.filter(date_joined__date__gte=last_30_days).count()
        
        return context


class ToggleUserStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Toggle user active/blocked status"""
    
    def test_func(self):
        """Only allow admin users"""
        return self.request.user.user_type.upper() == User.UserType.ADMIN
    
    def post(self, request):
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        
        try:
            user = User.objects.get(id=user_id)
            
            # Prevent admin from blocking themselves
            if user.id == request.user.id:
                messages.error(request, "You cannot block yourself!")
                return redirect('users:user_management')
            
            if action == 'block':
                user.is_active = False
                user.block_reason = request.POST.get('block_reason', '')
                user.save()
                messages.success(request, f"User {user.email} has been blocked successfully.")
            elif action == 'unblock':
                user.is_active = True
                user.block_reason = None
                user.save()
                messages.success(request, f"User {user.email} has been unblocked successfully.")
            else:
                messages.error(request, "Invalid action.")
        
        except User.DoesNotExist:
            messages.error(request, "User not found.")
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
        
        return redirect('users:user_management')


# View instances
user_management_view = UserManagementView.as_view()
toggle_user_status_view = ToggleUserStatusView.as_view()


from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.shortcuts import get_object_or_404
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from ai_debuger.users.models import User, ChatSession, ChatMessage, CodeSnippet
import json


class UserDetailView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Detailed view of a specific user for admins"""
    template_name = 'users/admin_user_detail.html'
    
    def test_func(self):
        """Only allow admin users"""
        return self.request.user.user_type.upper() == User.UserType.ADMIN
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the user
        user_id = self.kwargs.get('user_id')
        user_detail = get_object_or_404(User, id=user_id)
        
        # Date ranges
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)
        
        # Get user's sessions
        sessions = ChatSession.objects.filter(user=user_detail)
        messages = ChatMessage.objects.filter(session__user=user_detail)
        snippets = CodeSnippet.objects.filter(message__session__user=user_detail)
        
        # Calculate stats
        total_sessions = sessions.count()
        active_sessions = sessions.filter(is_active=True).count()
        total_messages = messages.count()
        total_snippets = snippets.count()
        
        # Average messages per session
        avg_messages = messages.values('session').annotate(
            msg_count=Count('id')
        ).aggregate(avg=Avg('msg_count'))['avg'] or 0
        
        # Get recent sessions
        recent_sessions = sessions.order_by('-created_at')[:10]
        
        # Language usage
        snippet_languages = snippets.values('language').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Activity chart data (last 30 days)
        activity_data = sessions.filter(
            created_at__date__gte=last_30_days
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Prepare chart data
        activity_chart = {
            'labels': [item['date'].strftime('%b %d') for item in activity_data],
            'data': [item['count'] for item in activity_data],
        }
        
        language_chart = {
            'labels': [item['language'] for item in snippet_languages],
            'data': [item['count'] for item in snippet_languages],
        }
        
        # Add to context
        context['user_detail'] = user_detail
        context['total_sessions'] = total_sessions
        context['active_sessions'] = active_sessions
        context['total_messages'] = total_messages
        context['total_snippets'] = total_snippets
        context['avg_messages_per_session'] = round(avg_messages, 1)
        context['recent_sessions'] = recent_sessions
        context['snippet_languages'] = snippet_languages
        context['activity_chart'] = json.dumps(activity_chart)
        context['language_chart'] = json.dumps(language_chart)
        
        return context


# View instance
admin_user_detail_view = UserDetailView.as_view()

# Forgot Password and Reset Password Views

SMTP_HOST = "smtp.zoho.in"
SMTP_PORT = 587
EMAIL_SENDER = "info@cudiort.com"
EMAIL_PASSWORD = "Karthikeyansp123$"

def send_reset_email(to_email, reset_link):
    subject = "Password Reset Request - DebugAI"
    body = f"""Hello,

You requested a password reset for your DebugAI account.
Please click the link below to reset your password. 
This link will expire in 5 minutes.

Reset Link: {reset_link}

If you did not request this, please ignore this email.
"""
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
            print(f"Reset email sent to {to_email}")
            return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

class ForgotPasswordView(View):
    template_name = "auth/forgot_password.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip()
        if not email:
            messages.error(request, "Email is required")
            return render(request, self.template_name)

        try:
            user = User.objects.get(email=email)
            token = str(uuid.uuid4())
            expires_at = timezone.now() + timedelta(minutes=5)
            
            from .models import PasswordResetToken
            PasswordResetToken.objects.create(
                user=user,
                token=token,
                expires_at=expires_at
            )

            # Build reset link
            protocol = 'https' if request.is_secure() else 'http'
            domain = request.get_host()
            reset_link = f"{protocol}://{domain}/reset-password/{token}/"

            if send_reset_email(email, reset_link):
                messages.success(request, "A reset link has been sent to your email. It expires in 5 minutes.")
            else:
                messages.error(request, "Failed to send reset email. Please try again later.")
            
            return redirect("/")
        except User.DoesNotExist:
            # For security, don't reveal if user exists. 
            messages.success(request, "If an account exists with that email, a reset link has been sent.")
            return redirect("/")

class ResetPasswordView(View):
    template_name = "auth/reset_password.html"

    def get(self, request, token):
        from .models import PasswordResetToken
        try:
            reset_token = PasswordResetToken.objects.get(token=token, is_used=False)
            if reset_token.is_expired():
                messages.error(request, "The reset link has expired.")
                return redirect("/")
            
            # Calculate remaining time for the timer
            remaining_seconds = int((reset_token.expires_at - timezone.now()).total_seconds())
            return render(request, self.template_name, {
                'token': token,
                'remaining_seconds': max(0, remaining_seconds)
            })
        except PasswordResetToken.DoesNotExist:
            messages.error(request, "Invalid reset link.")
            return redirect("/")

    def post(self, request, token):
        from .models import PasswordResetToken
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long")
            return render(request, self.template_name, {'token': token})

        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return render(request, self.template_name, {'token': token})

        try:
            reset_token = PasswordResetToken.objects.get(token=token, is_used=False)
            if reset_token.is_expired():
                messages.error(request, "The reset link has expired.")
                return redirect("/")

            user = reset_token.user
            user.set_password(password)
            user.save()

            reset_token.is_used = True
            reset_token.save()

            messages.success(request, "Password reset successful! You can now log in.")
            return redirect("/")
        except PasswordResetToken.DoesNotExist:
            messages.error(request, "Invalid reset link.")
            return redirect("/")

forgot_password_view = ForgotPasswordView.as_view()
reset_password_view = ResetPasswordView.as_view()