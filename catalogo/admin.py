from django.contrib import admin

from .models import Plan, Zona


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre", "descripcion")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("nombre", "mbps_bajada", "mbps_subida", "precio_mensual", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)
