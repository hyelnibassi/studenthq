from django import forms
from .models import User, Student, Course, InstallmentPlan, Payment
import json


class LoginForm(forms.Form):
    email    = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'your@aun.edu.ng'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class FeeCalculatorForm(forms.Form):
    credit_hours = forms.IntegerField(
        min_value=1, max_value=24,
        label='Number of Credit Hours',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 15'})
    )
    accommodation = forms.ChoiceField(
        choices=[('on-campus', 'On-Campus'), ('off-campus', 'Off-Campus'), ('none', 'None')],
        label='Accommodation Type',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    include_sports  = forms.BooleanField(required=False, label='Sports Fee (₦15,000)')
    include_lab     = forms.BooleanField(required=False, label='Lab Fee (₦25,000)')
    include_library = forms.BooleanField(required=False, label='Library Fee (₦20,000)')
    months_overdue  = forms.IntegerField(min_value=0, initial=0, label='Months Overdue',
                                         widget=forms.NumberInput(attrs={'class': 'form-control'}))


class GPASimulatorForm(forms.Form):
    hypothetical_grades_json = forms.CharField(widget=forms.HiddenInput(), required=False)

    def clean_hypothetical_grades_json(self):
        raw = self.cleaned_data.get('hypothetical_grades_json', '[]')
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError('Invalid grade data format.')
