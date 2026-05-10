from django.urls import path

from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view
from .views import settings_view
from.views import (login_view, sign_up_view,
                   dashboard_view,
                   debugger_view,
                   debugger_answer_view,
                   clear_chat_view,
                   coding_assistant_view,
                   clear_all_chats_view,
                   new_chat_view,
                   delete_chat_view,
                   export_chat_view,
                   chat_list_view,
                   chat_detail_view,
                   logout_view,
                   admin_dashboard_view,
                   user_management_view,
                   toggle_user_status_view,
                   admin_user_detail_view,
                   debugger_feedback_view,
                   forgot_password_view,
                   reset_password_view
                   )

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("settings/", view=settings_view, name="settings"),
    path("<int:pk>/", view=user_detail_view, name="detail"),


    #user
    path("", view=login_view, name="login"),
    path("forgot-password/", view=forgot_password_view, name="forgot_password"),
    path("reset-password/<str:token>/", view=reset_password_view, name="reset_password"),
    path("signup/", view=sign_up_view, name="signup"),
    path("dashboard/", view=dashboard_view, name="dashboard"),

    
    path("debugger/", view=debugger_view, name="debugger"),

     path("debugger-answer/", view=debugger_answer_view, name="debugger_answer_view"),
     path("clear-chat/", view=clear_chat_view, name="clear_chat"),
   path(
        "coding-assistant/",
        coding_assistant_view,
        name="coding_assistant"
    ),
    path(
        "coding-assistant/new/",
        new_chat_view,
        name="new_chat"
    ),
    path(
        "coding-assistant/delete/<str:session_id>/",
        delete_chat_view,
        name="delete_chat"
    ),
    
        path(
        "chats/delete/<str:session_id>/",
        delete_chat_view,
        name="delete_chat"
    ),
        
        
    path(
        "coding-assistant/clear-all/",
        clear_all_chats_view,
        name="clear_all_chats"
    ),
    path(
        "coding-assistant/export/<str:session_id>/",
        export_chat_view,
        name="export_chat"
    ),

        
    # Chat History & Management
    path("chats/", chat_list_view, name="chat_list"),
    path("chats/<str:session_id>/", chat_detail_view, name="chat_detail"),
    path("logout/", logout_view, name="logout"),
     path("admin-dashboard/", admin_dashboard_view, name="admin_dashboard"),


         path("admin-user-management/", user_management_view, name="user_management"),
    path("admin-toggle-user-status/", toggle_user_status_view, name="toggle_user_status"),
    path("admin-user-detail/<int:user_id>/", admin_user_detail_view, name="user_detail"),
     path("debugger/feedback/", debugger_feedback_view, name="debugger_feedback"),




]
