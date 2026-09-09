from django import forms

from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nombre", "documento", "telefono", "email", "direccion", "coordenadas",
            "zona", "plan", "router", "ip", "nombre_cola", "dia_de_pago",
            "dia_de_corte", "estado", "forma_contratacion", "fecha_registro",
            "fecha_instalacion", "fecha_cancelacion", "notas",
        ]
        widgets = {
            "fecha_registro": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_instalacion": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_cancelacion": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notas": forms.Textarea(attrs={"rows": 3}),
            "direccion": forms.TextInput(),
        }

    # Grupos para mostrar el formulario por secciones en la plantilla.
    SECCIONES = [
        ("Datos personales", ["nombre", "documento", "telefono", "email", "direccion", "coordenadas"]),
        ("Servicio", ["zona", "plan", "router", "ip", "nombre_cola", "dia_de_pago", "dia_de_corte", "estado", "forma_contratacion"]),
        ("Fechas y comentarios", ["fecha_registro", "fecha_instalacion", "fecha_cancelacion", "notas"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs.setdefault("class", css)
        # IP: lista desplegable con las IPs libres de la zona elegida (la llena el JS)
        actual = self.instance.ip if self.instance and self.instance.pk else None
        choices = [("", "— elige primero la zona —")]
        if actual:
            choices.append((actual, actual))
        self.fields["ip"].widget = forms.Select(
            choices=choices, attrs={"class": "form-select", "id": "id_ip"},
        )
        self.fields["zona"].widget.attrs["id"] = "id_zona"

    def secciones(self):
        """Devuelve [(titulo, [BoundField, ...]), ...] para la plantilla."""
        return [(titulo, [self[n] for n in nombres]) for titulo, nombres in self.SECCIONES]

    def clean_dia_de_pago(self):
        dia = self.cleaned_data["dia_de_pago"]
        if not 1 <= dia <= 28:
            raise forms.ValidationError("Usa un día entre 1 y 28.")
        return dia

    def clean_dia_de_corte(self):
        dia = self.cleaned_data.get("dia_de_corte")
        if dia is not None and not 1 <= dia <= 28:
            raise forms.ValidationError("Usa un día entre 1 y 28, o déjalo vacío.")
        return dia
