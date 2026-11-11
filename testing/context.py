def role(request):
    return {'is_teacher': request.user.is_authenticated and request.user.groups.filter(name='Преподаватели').exists()}
