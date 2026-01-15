from django.db import models

class Donation(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]
    reference = models.CharField(max_length=64, unique=True)
    amount = models.PositiveIntegerField(help_text="Montant en plus petite unité (ex: XOF)")
    currency = models.CharField(max_length=8, default="XOF")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=24, blank=True, null=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    fedapay_transaction_id = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Donation {self.reference} - {self.amount} {self.currency} - {self.status}"
