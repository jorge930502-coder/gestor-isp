from django import forms

from .models import Router


class RouterForm(forms.ModelForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        obj = super().save(commit=False)
        nueva = self.cleaned_data.get("password")
        if nueva:
            obj.set_password(nueva)
        if commit:
            obj.save()
        return obj


class ImportarForm(forms.Form):
    FUENTES = [
        ("queues", "Colas simples (Simple Queues)"),
        ("ppp", "Usuarios PPPoE"),
        ("dhcp", "Leases DHCP"),
    ]
    router = forms.ModelChoiceField(
        queryset=Router.objects.filter(activo=True),
        required=False,
        label="Router",
        help_text="Elige un router guardado para conectarse por API.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    archivo = forms.FileField(
        required=False,
        label="o sube un archivo .rsc exportado del router",
        help_text="En el Mikrotik: /queue simple export file=colas  →  Files  →  colas.rsc",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    fuente = forms.ChoiceField(
        choices=FUENTES, initial="queues", label="De dónde leer",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    crear_planes = forms.BooleanField(
        required=False, initial=True, label="Crear planes automáticamente por velocidad",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean(self):
        data = super().clean()
        if not data.get("router") and not data.get("archivo"):
            raise forms.ValidationError(
                "Elige un router guardado o sube un archivo .rsc."
            )
        return data
