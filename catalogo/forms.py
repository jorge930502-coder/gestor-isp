from django import forms

from .models import Plan, Zona


def _bootstrap(form):
    for f in form.fields.values():
        w = f.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", "form-check-input")
        elif isinstance(w, forms.Select):
            w.attrs.setdefault("class", "form-select")
        else:
            w.attrs.setdefault("class", "form-control")


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = ["nombre", "mbps_bajada", "mbps_subida", "precio_mensual",
                  "descripcion", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)


class ZonaForm(forms.ModelForm):
    class Meta:
        model = Zona
        fields = ["nombre", "descripcion", "vlan", "red_cidr", "gateway", "activa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)
