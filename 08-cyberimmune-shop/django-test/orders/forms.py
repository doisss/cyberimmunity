from django import forms

# Форма оформления заказа
class OrderForm(forms.Form):
    name = forms.CharField(max_length=100)
    address = forms.CharField(max_length=255)
    item = forms.CharField(max_length=100)
    quantity = forms.IntegerField(min_value=1, max_value=1000)
