from django.utils.deprecation import MiddlewareMixin


class LoginAttemptMiddleware(MiddlewareMixin):
    """Expose compteur et état de verrouillage pour la page admin login."""
    FAIL_KEY = 'admin_login_fail_count'
    LOCK_UNTIL_KEY = 'admin_login_lock_until'
    FAIL_THRESHOLD = 3
    LOCK_MINUTES = 2

    def process_request(self, request):
        from django.utils import timezone
        # Initialisation compteur
        if self.FAIL_KEY not in request.session:
            request.session[self.FAIL_KEY] = 0
        fail_count = request.session.get(self.FAIL_KEY, 0)
        lock_until_ts = request.session.get(self.LOCK_UNTIL_KEY)
        locked = False
        remaining_seconds = 0
        if lock_until_ts:
            # lock_until_ts stocké en isoformat
            try:
                lock_until = timezone.datetime.fromisoformat(lock_until_ts)
                if timezone.now() < lock_until:
                    locked = True
                    delta = lock_until - timezone.now()
                    remaining_seconds = int(delta.total_seconds())
                else:
                    # Expiré : reset
                    request.session.pop(self.LOCK_UNTIL_KEY, None)
                    request.session[self.FAIL_KEY] = 0
                    fail_count = 0
            except Exception:
                # En cas de parsing foireux, suppression
                request.session.pop(self.LOCK_UNTIL_KEY, None)
        request.login_fail_count = fail_count
        request.login_locked = locked
        request.login_lock_remaining = remaining_seconds
