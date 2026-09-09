from django.urls import path

from . import views

app_name = "facturacion"

urlpatterns = [
    path("facturas/", views.facturas, name="facturas"),
    path("factura/<int:pk>/", views.factura_detalle, name="factura_detalle"),
    path("facturas/generar/", views.generar, name="generar"),
    path("facturas/recalcular/", views.recalcular, name="recalcular"),
    path("pagos/", views.pagos, name="pagos"),
    path("pagos/registrar/", views.registrar_pago, name="registrar_pago"),
    path("pagos/lote/", views.pago_lote, name="pago_lote"),
    path("morosos/", views.morosos, name="morosos"),
    path("facturas/<int:pk>/anular/", views.factura_anular, name="factura_anular"),
    path("facturas/<int:pk>/eliminar/", views.factura_eliminar, name="factura_eliminar"),
    path("pagos/<int:pk>/eliminar/", views.pago_eliminar, name="pago_eliminar"),
    path("adicional/<int:cliente_pk>/agregar/", views.adicional_agregar, name="adicional_agregar"),
    path("adicional/<int:pk>/eliminar/", views.adicional_eliminar, name="adicional_eliminar"),
]
