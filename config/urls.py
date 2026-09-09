from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from core.views import config as config_view, dashboard, portal

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "acceder/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("tablero/", dashboard, name="dashboard"),
    path("config/", config_view, name="config"),
    path("portal/", portal, name="portal"),
    path("portal", portal),
    path("clientes/", include("clientes.urls")),
    path("red/", include("red.urls")),
    path("finanzas/", include("facturacion.urls")),
    path("catalogo/", include("catalogo.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
