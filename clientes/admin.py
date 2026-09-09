from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "telefono", "zona", "plan", "ip", "dia_de_pago", "dia_de_corte", "estado")
    list_filter = ("estado", "zona", "plan")
    search_fields = ("nombre", "documento", "telefono", "email", "ip", "direccion")
    autocomplete_fields = ("zona", "plan")
    readonly_fields = ("creado", "actualizado", "creado_por")
    fieldsets = (
        ("Datos personales", {
            "fields": ("nombre", "documento", "telefono", "email", "direccion"),
        }),
        ("Servicio", {
            "fields": ("zona", "plan", "router", "ip", "nombre_cola", "dia_de_pago", "dia_de_corte", "estado", "fecha_instalacion"),
        }),
        ("Otros", {
            "fields": ("notas", "creado", "actualizado", "creado_por"),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.creado_por_id:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)
