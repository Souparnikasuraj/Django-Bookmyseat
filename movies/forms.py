from django import forms
from .models import Review, ReviewReport


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(
                choices=[
                    (1, '⭐ 1'),
                    (2, '⭐⭐ 2'),
                    (3, '⭐⭐⭐ 3'),
                    (4, '⭐⭐⭐⭐ 4'),
                    (5, '⭐⭐⭐⭐⭐ 5'),
                ]
            ),
            'comment': forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': 'Write your review...'
                }
            ),
        }

    def clean_rating(self):
        rating = self.cleaned_data['rating']

        if rating < 1 or rating > 5:
            raise forms.ValidationError(
                "Rating must be between 1 and 5."
            )

        return rating
    

class ReviewReportForm(forms.ModelForm):
    class Meta:
        model = ReviewReport
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': 'Why are you reporting this review?'
                }
            )
        }