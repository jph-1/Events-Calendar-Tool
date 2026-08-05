"""Login-required decorator, shared by every other route module."""
from __future__ import annotations

import functools

from flask import redirect, request, url_for

from events_tool.web import get_current_user


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped
