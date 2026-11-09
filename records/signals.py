"""Audit trail: every create/update/delete of an academic record is logged."""
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from academics.models import AcademicSession, Course

from .middleware import client_ip, get_current_ip, get_current_user
from .models import AuditLog, Registration, Result, Student

AUDITED_MODELS = (Student, Course, Registration, Result, AcademicSession)
IGNORED_FIELDS = {"updated_at", "created_at", "registered_at"}


def _field_values(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS:
            continue
        values[field.name] = getattr(instance, field.attname)
    return values


def _log(action, instance, changes=""):
    AuditLog.objects.create(
        user=get_current_user(),
        action=action,
        model_name=instance._meta.verbose_name.title(),
        object_id=str(instance.pk or ""),
        object_repr=str(instance)[:255],
        changes=changes,
        ip_address=get_current_ip(),
    )


@receiver(pre_save)
def capture_old_values(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS or not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).first()
    instance._audit_old = _field_values(old) if old else None


@receiver(post_save)
def log_save(sender, instance, created, raw=False, **kwargs):
    if sender not in AUDITED_MODELS or raw:
        return
    if created:
        _log(AuditLog.Action.CREATE, instance)
        return
    old = getattr(instance, "_audit_old", None) or {}
    new = _field_values(instance)
    diffs = [
        f"{name}: {old.get(name)!s} -> {value!s}"
        for name, value in new.items()
        if name in old and str(old.get(name)) != str(value)
    ]
    if diffs:
        _log(AuditLog.Action.UPDATE, instance, "; ".join(diffs))


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    if sender in AUDITED_MODELS:
        _log(AuditLog.Action.DELETE, instance)


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.LOGIN,
        model_name="User",
        object_id=str(user.pk),
        object_repr=str(user)[:255],
        ip_address=client_ip(request) if request else None,
    )
