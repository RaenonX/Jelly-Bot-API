from django.views import View
from django.utils.translation import gettext_lazy as _

from doc import terms_collection
from JellyBot.views.render import render_template


class TermsExplanationView(View):
    # noinspection PyUnusedLocal, PyMethodMayBeStatic, PyTypeChecker
    def get(self, request, *args, **kwargs):
        return render_template(request, _("Terms Explanation"), "doc/terms.html",
                               {"terms_collection": terms_collection})
