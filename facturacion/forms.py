from django import forms
from django.utils import timezone

from clientes.models import Cliente

from .models import Pago


def _bootstrap(form):
    for field in form.fields.values():
        w = field.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", "form-check-input")
        elif isinstance(w, forms.Select):
            w.attrs.setdefault("class", "form-select")
        else:
            w.attrs.setdefault("class", "form-control")


class PagoForm(forms.ModelForm):
    reactivar = forms.BooleanField(
        required=False, initial=True,
        label="Reactivar el servicio si estaba suspendido",
    )

    class Meta:
        model = Pago
        fields = ["fecha", "monto", "metodo", "referencia", "nota"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("fecha", timezone.localdate())
        _bootstrap(self)


class PagoRapidoForm(PagoForm):
    """Igual que PagoForm pero pidiendo también el cliente."""

    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.exclude(estado=Cliente.Estado.CANCELADO).order_by("nombre"),
        label="Cliente",
    )

    field_order = ["cliente", "fecha", "monto", "metodo", "referencia", "nota", "reactivar"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)
