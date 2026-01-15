from django.contrib.auth.signals import user_login_failed, user_logged_in
from django.dispatch import receiver
from django.utils import timezone

FAIL_KEY = 'admin_login_fail_count'
LOCK_UNTIL_KEY = 'admin_login_lock_until'
FAIL_THRESHOLD = 3
LOCK_MINUTES = 2

@receiver(user_login_failed)
def login_failed(sender, credentials, request, **kwargs):  # type: ignore
    if request is None:
        return
    # Si déjà verrouillé, ne pas incrémenter
    lock_until = request.session.get(LOCK_UNTIL_KEY)
    if lock_until:
        try:
            if timezone.now() < timezone.datetime.fromisoformat(lock_until):
                return
        except Exception:
            request.session.pop(LOCK_UNTIL_KEY, None)
    count = request.session.get(FAIL_KEY, 0) + 1
    request.session[FAIL_KEY] = count
    if count >= FAIL_THRESHOLD:
        # Définir verrouillage
        lock_time = timezone.now() + timezone.timedelta(minutes=LOCK_MINUTES)
        request.session[LOCK_UNTIL_KEY] = lock_time.isoformat()

@receiver(user_logged_in)
def login_success(sender, request, user, **kwargs):  # type: ignore
    if request is None:
        return
    for key in (FAIL_KEY, LOCK_UNTIL_KEY):
        if key in request.session:
            request.session.pop(key, None)