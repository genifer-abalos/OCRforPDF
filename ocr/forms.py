from django import forms


class FileUploadForm(forms.Form):
    file = forms.FileField()


REPORT_CHOICES = [
        ('sg', 'SG - Specific Gravity'),
        ('cs', 'CS - Corrosive Sulfur'),
        ('tca', '*TCA - Transformer Condition Assessment'),
        ('lubecheck', '*Lubecheck Oil Analysis'),
    ]


SERVER_CHOICES = [
        ('bacman', 'Bacman'),
        ('leyte', 'Leyte'),
        ('mtapo', 'Mt. Apo'),
        ('negros', 'Negros'),
    ]


class ReportDropdown(forms.Form):
    report_type = forms.CharField(label='Which report to upload?', widget=forms.Select(choices=REPORT_CHOICES))


class ServerDropdown(forms.Form):
    server_site = forms.CharField(label='Site ', widget=forms.Select(choices=SERVER_CHOICES))


class SubmitData(forms.Form):
    # fetched_data = forms.CharField()
    fetched_data = forms.CharField(required=True)
