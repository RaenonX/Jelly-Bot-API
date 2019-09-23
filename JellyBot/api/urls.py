from django.urls import path
from django.urls import include

from .status import status_check
from .tkact import TokenActionCompleteView, TokenActionListView
from .webhook import WebhookLineView, DirectMessageWebhookView

urlpatterns = [
    path('status/', status_check, name='JellyBotAPI.api.status'),
    path('ar/', include('JellyBot.api.ar.urls')),
    path('id/', include('JellyBot.api.id.urls')),
    path('token', TokenActionCompleteView.as_view(), name="api.token.complete"),
    path('token/list', TokenActionListView.as_view(), name="api.token.list"),
    path('webhook/line', WebhookLineView.as_view(), name="api.webhook.line"),
    path('webhook/direct/text', DirectMessageWebhookView.as_view(), name="api.webhook.direct.text")
]