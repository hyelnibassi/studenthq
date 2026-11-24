from .models import AuditLog


def log_action(user, action, description, request=None):
    """
    Create an audit log entry.
    user:        User model instance (can be None for anonymous actions)
    action:      one of AuditLog.ACTION_CHOICES keys
    description: plain text description of what happened
    request:     Django request object — used to extract IP address
    """
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')

    AuditLog.objects.create(
        user=user,
        action=action,
        description=description,
        ip_address=ip,
    )
