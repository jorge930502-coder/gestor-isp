from django.contrib import admin

from .models import Factura, Pago, ServicioAdicional


@admin.register(ServicioAdicional)
class ServicioAdicionalAdmin(admin.ModelAdmin):
    list_display = ("cliente", "concepto", "monto", "activo")
    list_filter = ("concepto", "activo")
    search_fields = ("cliente__nombre",)
    autocomplete_fields = ("cliente",)


class PagoInline(admin.TabularInline):
    model = Pago
    extra = 0
    fields = ("fecha", "monto", "metodo", "referencia", "registrado_por")
    readonly_fields = ("registrado_por",)


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ("cliente", "periodo_texto", "monto", "vencimiento", "corte", "estado")
    list_filter = ("estado", "periodo")
    search_fields = ("cliente__nombre", "cliente__ip")
    date_hierarchy = "periodo"
    inlines = [PagoInline]
    autocomplete_fields = ("cliente",)


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "fecha", "monto", "metodo", "factura", "registrado_por")
    list_filter = ("metodo", "fecha")
    search_fields = ("cliente__nombre", "referencia")
    date_hierarchy = "fecha"
    autocomplete_fields = ("cliente", "factura")

    def save_model(self, request, obj, form, change):
        if not obj.registrado_por_id:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)
        if obj.factura_id:
            obj.factura.recalcular_estado()
