from django.http import JsonResponse
from django.views import View
from django.utils.translation import gettext_lazy as _

from JellyBot.components.mixin import CsrfExemptMixin
from JellyBot.api.static import param
from JellyBot.views import simple_str_response
from extutils.serializer import JellyBotAPISerializer
from external.handle import EventObjectFactory, handle_main


class DirectMessageWebhookView(CsrfExemptMixin, View):
    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, *args, **kwargs):
        msg = request.GET.get(param.Message.MESSAGE)
        if msg:
            return JsonResponse(
                handle_main(EventObjectFactory.from_direct(msg)).to_json(), encoder=JellyBotAPISerializer)
        else:
            return simple_str_response(request, _(f"Provide {param.Message.MESSAGE} as a query parameter for message."))