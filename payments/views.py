import os
import json
import secrets
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.encoding import force_bytes
import hmac, hashlib
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from .models import Donation

# NOTE: Remplacer par SDK FedaPay réel si disponible dans l'environnement.
# Ici on structure le flux et on simulera l'appel API (à brancher ensuite).

# ATTENTION: Contient des valeurs par défaut codées en dur pour faciliter les tests sur cet environnement.
# Pour la production, il est fortement recommandé d'utiliser des variables d'environnement et de NE PAS committer
# des clés réelles dans le dépôt.
# Ordre de chargement: variable d'environnement si définie, sinon valeur codée ci-dessous.
FEDAPAY_PUBLIC_KEY = os.environ.get('FEDAPAY_PUBLIC_KEY') or 'pk_sandbox_EX4uz1Sj2YF_WBeKlai_xAVc'
FEDAPAY_SECRET_KEY = os.environ.get('FEDAPAY_SECRET_KEY') or 'sk_sandbox_Nbv3pxyYc0u8VDLOo3G4-jQD'
FEDAPAY_MODE = os.environ.get('FEDAPAY_MODE') or 'sandbox'  # 'live' en prod
FEDAPAY_WEBHOOK_SECRET = os.environ.get('FEDAPAY_WEBHOOK_SECRET') or 'wh_sandbox__K5qQY-4K_Qv43NW_3QTvZHp'
# Dev only: permet de désactiver la vérification de signature du webhook (1/true/yes)
FEDAPAY_WEBHOOK_DISABLE_VERIFY = (os.environ.get('FEDAPAY_WEBHOOK_DISABLE_VERIFY', '').strip().lower() in ('1', 'true', 'yes'))


def start_checkout(request):
    # Accepter POST (form) et GET (fallback via lien direct ou test) avec query ?amount=...
    amt_str = request.POST.get('amount') if request.method == 'POST' else request.GET.get('amount')
    if not amt_str:
        amt_str = '1000'
    try:
        amount = int(amt_str)
    except (TypeError, ValueError):
        amount = 1000

    # borne minimale simple
    if amount < 100:
        amount = 100

    currency = (request.POST.get('currency') if request.method == 'POST' else request.GET.get('currency')) or 'XOF'

    # Générer une référence unique côté EEJ (pour recoller via webhook)
    reference = secrets.token_hex(10)

    Donation.objects.create(
        reference=reference,
        amount=amount,
        currency=currency,
        status='pending'
    )

    success_url = request.build_absolute_uri(reverse('payments:success'))
    cancel_url = request.build_absolute_uri(reverse('payments:cancel'))

    # Rendre une page qui initialise Checkout.js et ouvre la fenêtre de paiement
    context = {
        'public_key': FEDAPAY_PUBLIC_KEY,
        'environment': FEDAPAY_MODE,
        'amount': amount,
        'currency': currency,
        'description': 'Don ONG EEJ',
        'metadata_ref': reference,
        'success_url': success_url,
        'cancel_url': cancel_url,
    }
    return render(request, 'payments/checkout.html', context)


def success(request):
    messages.success(request, "Merci pour votre soutien ❤️ Votre paiement a bien été reçu.")
    return redirect('website:donate')


def cancel(request):
    messages.warning(request, "Paiement annulé. Vous pouvez réessayer quand vous voulez.")
    return redirect('website:donate')


@csrf_exempt
def webhook(request):
    # Vérifier la signature si fournie par FedaPay (header), puis parser l'événement
    signature = request.headers.get('FedaPay-Signature') or request.headers.get('Fedapay-Signature')
    payload = request.body.decode('utf-8')
    if FEDAPAY_WEBHOOK_SECRET and not FEDAPAY_WEBHOOK_DISABLE_VERIFY:
        # Essai avec SDK s'il expose un vérificateur; sinon HMAC-SHA256 simple
        is_valid = False
        if signature:
            try:
                # Certain SDKs exposent fedapay.WebhookSignature.verify_header(payload, header, secret)
                from fedapay import WebhookSignature
                try:
                    WebhookSignature.verify_header(payload, signature, FEDAPAY_WEBHOOK_SECRET)
                    is_valid = True
                except Exception:
                    is_valid = False
            except Exception:
                # Fallback HMAC (à adapter selon le schéma de signature réel si nécessaire)
                digest = hmac.new(force_bytes(FEDAPAY_WEBHOOK_SECRET), force_bytes(payload), hashlib.sha256).hexdigest()
                is_valid = (digest == signature) or (('t=' in signature) and (digest in signature))
        if not is_valid:
            return HttpResponseBadRequest('Signature invalide')
    try:
        data = json.loads(payload or '{}')
    except Exception:
        return HttpResponseBadRequest('Payload invalide')

    # Extraction robuste des champs utiles (référence, statut, id) selon différentes structures possibles
    def deep_find(obj, keys):
        # Retourne la première valeur trouvée pour l'une des clés dans un dict/list imbriqué
        if isinstance(obj, dict):
            for k in keys:
                if k in obj and obj[k] is not None:
                    return obj[k]
            for v in obj.values():
                res = deep_find(v, keys)
                if res is not None:
                    return res
        elif isinstance(obj, list):
            for it in obj:
                res = deep_find(it, keys)
                if res is not None:
                    return res
        return None

    # Certains envois ont data.object, d'autres peuvent être à plat ou sous "transaction"
    tx = data.get('data', {}).get('object') or data.get('transaction') or data
    # Référence: priorité à notre eej_ref dans custom_metadata/metadata, sinon reference générique
    reference = deep_find(tx, ['eej_ref'])
    if not reference:
        reference = deep_find(tx, ['reference'])
    status = deep_find(tx, ['status'])
    fedapay_id_val = deep_find(tx, ['id'])
    fedapay_id = str(fedapay_id_val or '')

    # Log simple pour debug (console)
    try:
        print('[FedaPay webhook] ref=', reference, 'status=', status, 'id=', fedapay_id)
    except Exception:
        pass

    if not reference:
        # En mode debug (disable verify), on ne bloque pas pour faciliter le diagnostic
        if FEDAPAY_WEBHOOK_DISABLE_VERIFY:
            return HttpResponse('ok')
        return HttpResponseBadRequest('Référence manquante')

    try:
        donation = Donation.objects.get(reference=reference)
    except Donation.DoesNotExist:
        if FEDAPAY_WEBHOOK_DISABLE_VERIFY:
            return HttpResponse('ok')
        return HttpResponseBadRequest('Donation inconnue')

    # Mapper les statuts FedaPay aux nôtres
    mapping = {
        'approved': 'paid',
        'paid': 'paid',
        'canceled': 'canceled',
        'failed': 'failed',
    }
    new_status = mapping.get(status)
    if new_status:
        donation.status = new_status
        donation.fedapay_transaction_id = fedapay_id
        donation.save(update_fields=['status', 'fedapay_transaction_id', 'updated_at'])

    return HttpResponse('ok')


@staff_member_required
def donations_list(request):
    qs = Donation.objects.order_by('-created_at')[:100]
    counts = {
        'total': Donation.objects.count(),
        'paid': Donation.objects.filter(status='paid').count(),
        'pending': Donation.objects.filter(status='pending').count(),
        'failed': Donation.objects.filter(status='failed').count(),
        'canceled': Donation.objects.filter(status='canceled').count(),
    }
    return render(request, 'payments/donations_list.html', { 'donations': qs, 'counts': counts })


@staff_member_required
def fedapay_debug(request):
    def mask(s, show=6):
        if not s:
            return ''
        return s[:show] + '…' + s[-4:]
    ctx = {
        'public_key': mask(FEDAPAY_PUBLIC_KEY),
        'mode': FEDAPAY_MODE,
        'webhook_secret_set': bool(FEDAPAY_WEBHOOK_SECRET),
    }
    return render(request, 'payments/fedapay_debug.html', ctx)
