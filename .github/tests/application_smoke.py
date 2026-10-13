"""Check dependency upgrades with an isolated database and real Django views."""

import runpy
import secrets
import sys
import tempfile
import types
from pathlib import Path

repository = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repository))

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

configuration = runpy.run_path(str(repository / "webvirtcloud/settings.py.template"))
configuration = {key: value for key, value in configuration.items() if key.isupper()}
configuration["SECRET_KEY"] = secrets.token_urlsafe(50)
configuration["DATABASES"] = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
configuration["ALLOWED_HOSTS"] = ["testserver"]
configuration["LOGGING"] = {"version": 1, "disable_existing_loggers": False}

with tempfile.TemporaryDirectory(prefix="webvirtcloud-smoke-") as temporary:
    configuration["BS_ICONS_CACHE"] = Path(temporary) / "icons"
    configuration["BS_ICONS_CACHE"].mkdir()
    # Existing application code imports the configured module directly.
    # Keep this fixture in memory so no deployment settings or secrets are written.
    configured_module = types.ModuleType("webvirtcloud.settings")
    configured_module.__dict__.update(configuration)
    sys.modules[configured_module.__name__] = configured_module
    settings.configure(**configuration)
    django.setup()
    call_command("check", verbosity=0)
    call_command("migrate", interactive=False, verbosity=0)

    client = Client()
    assert client.get(reverse("accounts:login")).status_code == 200
    password = secrets.token_urlsafe(32)
    user = get_user_model().objects.create_user("ci-dependency-smoke", password=password)
    assert client.login(username=user.username, password=password)
    assert client.get(reverse("accounts:profile")).status_code == 200
    assert client.get(reverse("schema-swagger-ui")).status_code == 200
    response = client.get(reverse("schema-json", kwargs={"format": ".json"}))
    assert response.status_code == 200
    assert response.json()["swagger"] == "2.0"

    import socketio
    import libvirt

    socketio.Server(async_mode="threading")
    connection = libvirt.open("test:///default")
    assert connection is not None
    assert connection.getType() == "TEST"
    connection.close()

print("Django checks, migrations, login/profile, API schema, Socket.IO and libvirt test driver passed")
