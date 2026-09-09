from django import forms
from django.contrib import admin

from .models import Router


class RouterAdminForm(forms.ModelForm):
    password = forms.CharField(
        label="contraseña",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Déjala en blanco para no cambiarla.",
    )

    class Meta:
        model = Router
        fields = [
            "nombre", "host", "api_puerto", "usa_tls", "usuario",
            "password", "lista_morosos", "activo", "notas",
        ]

    def save(self, commit=True):
        obj = super().save(commit=False)
        nueva = self.cleaned_data.get("password")
        if nueva:
            obj.set_password(nueva)
        if commit:
            obj.save()
        return obj


@admin.register(Router)
class RouterAdmin(admin.ModelAdmin):
    form = RouterAdminForm
    list_display = ("nombre", "host", "api_puerto", "usa_tls", "usuario", "activo")
    list_filter = ("activo", "usa_tls")
    search_fields = ("nombre", "host")
