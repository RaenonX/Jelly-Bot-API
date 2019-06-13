from django.http import HttpResponse
from django.shortcuts import render
from django.template import Template, RequestContext

from JellyBotAPI import keys
from JellyBotAPI.views.nav import construct_nav
from JellyBotAPI.api.static import result, param, anchor
from extutils.flags import FlagCodeMixin, FlagSingleMixin, FlagDoubleMixin


def render_template(request, title, template_name, context=None, content_type=None, status=None,
                    using=None) -> HttpResponse:
    if context is None:
        context = dict()

    # Append variable for base template
    context["title"] = title

    # Append navigation bar items
    nav = construct_nav(request)
    context["nav_bar_html"] = nav.to_html()
    context["nav_bread"] = nav.to_bread()
    context["static_keys_result"] = result
    context["static_keys_param"] = param
    context["static_keys_anchor"] = anchor

    # Append vars
    context["api_token"] = request.COOKIES.get(keys.USER_TOKEN)

    # Append necessary backend vars
    # INCOMPLETE: Permission: Construct an array and import here for unlocking elements
    context["unlock_classes"] = [keys.LOGGED_IN_ENABLE]

    return render(request, template_name, context, content_type, status, using)


def render_flag_table(request, title: str, table_title: str, flag_enum: type(FlagCodeMixin), context: dict = None,
                      content_type=None, status=None, using=None) -> HttpResponse:
    if context is None:
        context = dict()

    if not issubclass(flag_enum, FlagCodeMixin):
        raise ValueError(f"flag_enum ({flag_enum}) is not the subclass of `Flag`.")

    context["has_key"] = issubclass(flag_enum, FlagSingleMixin)
    context["has_description"] = issubclass(flag_enum, FlagDoubleMixin)

    context.update(**{"table_title": table_title,
                      "flags": list(flag_enum)})

    return render_template(request, title, "doc/code/generic.html", context, content_type, status, using)


def simple_str_response(request, s):
    return HttpResponse(Template("{{result}}").render(RequestContext(request, {"result": s})))
