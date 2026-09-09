from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.ClienteListView.as_view(), name="lista"),
    path("nuevo/", views.ClienteCreateView.as_view(), name="crear"),
    path("ips-libres/", views.ips_libres, name="ips_libres"),
    path("asignar/", views.asignar_lote, name="asignar_lote"),
    path("en-linea/", views.en_linea, name="en_linea"),
    path("<int:pk>/", views.ClienteDetailView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.ClienteUpdateView.as_view(), name="editar"),
    path("<int:pk>/consumo/", views.consumo, name="consumo"),
    path("<int:pk>/consumo/datos/", views.consumo_datos, name="consumo_datos"),
    path("<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("<int:pk>/whatsapp/", views.whatsapp_cobro, name="whatsapp_cobro"),
    path("<int:pk>/enviar-router/", views.enviar_al_router, name="enviar_al_router"),
]
