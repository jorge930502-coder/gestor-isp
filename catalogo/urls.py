from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("planes/", views.planes, name="planes"),
    path("planes/nuevo/", views.plan_form, name="plan_crear"),
    path("planes/<int:pk>/editar/", views.plan_form, name="plan_editar"),
    path("planes/<int:pk>/eliminar/", views.plan_eliminar, name="plan_eliminar"),
    path("zonas/", views.zonas, name="zonas"),
    path("zonas/nueva/", views.zona_form, name="zona_crear"),
    path("zonas/<int:pk>/editar/", views.zona_form, name="zona_editar"),
    path("zonas/<int:pk>/eliminar/", views.zona_eliminar, name="zona_eliminar"),
]
