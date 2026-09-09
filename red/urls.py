from django.urls import path

from . import views

app_name = "red"

urlpatterns = [
    path("routers/", views.routers, name="routers"),
    path("routers/nuevo/", views.router_form, name="router_crear"),
    path("routers/<int:pk>/editar/", views.router_form, name="router_editar"),
    path("routers/<int:pk>/probar/", views.router_probar, name="router_probar"),
    path("importar/", views.importar, name="importar"),
    path("cortes/", views.sincronizar_cortes, name="sincronizar_cortes"),
    path("colas/", views.sincronizar_colas, name="sincronizar_colas"),
    path("portal-router/", views.configurar_portal_router, name="configurar_portal"),
    path("trafico/", views.trafico, name="trafico"),
    path("trafico/datos/", views.trafico_datos, name="trafico_datos"),
]
