from .models import User

def logged_in_user(request):
    uid = request.session.get('user_id')
    if not uid:
        return {'user': None}
    try:
        user = User.objects.get(userID=uid)
        return {'user': user}
    except User.DoesNotExist:
        return {'user': None}