from django import forms

from .models import Config


class ConfigForm(forms.ModelForm):
    class Meta:
        model = Config
        fields = ["nombre_empresa", "logo", "whatsapp", "telefono", "instrucciones_pago",
                  "mensaje_whatsapp", "pie_factura", "portal_host",
                  "wa_phone_id", "wa_api_token"]
        widgets = {
            "instrucciones_pago": forms.Textarea(attrs={"rows": 4}),
            "mensaje_whatsapp": forms.Textarea(attrs={"rows": 5}),
            "pie_factura": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-control")
